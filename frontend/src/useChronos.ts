/**
 * useChronos.ts — React hook that manages the WebSocket connection to the
 * Chronos backend, scene state, and audio playback of Gemini Live responses.
 *
 * Full interaction flow:
 *   1. User sends scene_request  → receives scene_plan_update (ScenePlan)
 *   2. User sends npc_interact   → receives cutscene_start (intro narration)
 *   3. User speaks / sends audio → active Gemini Live NPC session responds
 *   4. User sends npc_leave      → NPC session closes, general session resumes
 *   5. User sends scene_exit     → receives status { scene_exited: true }
 */
import { useCallback, useEffect, useRef, useState } from 'react'

// ---------------------------------------------------------------------------
// Types (mirror backend models.py)
// ---------------------------------------------------------------------------

export interface NPCBase {
  npc_id: string
  name: string
  role: string
  position: [number, number, number]
  rotation: [number, number, number]
  mood: string
  action: string
  dialogue: string
}

export interface SceneObjectBase {
  object_id: string
  asset: string
  position: [number, number, number]
  rotation: [number, number, number]
  scale: [number, number, number]
}

export interface SceneState {
  session_id: string
  description: string
  npcs: NPCBase[]
  objects: SceneObjectBase[]
  ambient_sound: string
  lighting: string
}

// ---------------------------------------------------------------------------
// ScenePlan types (mirror backend models.py ScenePlan hierarchy)
// ---------------------------------------------------------------------------

export interface Position3D {
  x: number
  y: number
  z: number
}

export interface Fog {
  color: string
  near: number
  far: number
}

export interface Room {
  width: number
  depth: number
  height: number
  fog: Fog
  ambient_color: string
}

export interface Material {
  color: string
  roughness: number
  emissive_color?: string | null
}

export interface Prop {
  id: string
  shape: 'box' | 'sphere' | 'cylinder'
  dimensions: [number, number, number]
  position: Position3D
  material: Material
  interactable: boolean
  interact_type?: 'read' | 'inspect' | null
  interact_text?: string | null
  interact_content?: string | null
}

export interface Character {
  id: string
  name: string
  role: string
  position: Position3D
  head_portrait_prompt: string
  persona_summary: string
  interact_text: string
  primary: boolean
}

export interface Light {
  type: 'point' | 'spot' | 'ambient'
  position: Position3D
  color: string
  intensity: number
}

export interface CameraStart {
  x: number
  y: number
  z: number
}

export interface ScenePlan {
  scene_id: string
  event_name: string
  dramatic_moment: string
  room: Room
  lights: Light[]
  props: Prop[]
  characters: Character[]
  ambient_sounds: string[]
  intro_narration: string
  camera_start: CameraStart
}

export interface CutsceneData {
  intro_narration: string
  character_name: string
}

type WSMessageType =
  | 'audio_chunk'
  | 'text_input'
  | 'scene_request'
  | 'npc_interact'
  | 'npc_leave'
  | 'scene_exit'
  | 'scene_update'
  | 'scene_plan_update'
  | 'audio_output'
  | 'transcript'
  | 'error'
  | 'status'
  | 'cutscene_start'

interface WSMessage {
  type: WSMessageType
  payload?: unknown
}

// ---------------------------------------------------------------------------
// Audio playback helper (PCM → Web Audio)
// ---------------------------------------------------------------------------

function playPcmChunk(audioCtx: AudioContext, data: number[]): void {
  const int16 = new Int16Array(data)
  const float32 = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768
  }
  const buffer = audioCtx.createBuffer(1, float32.length, 24000)
  buffer.copyToChannel(float32, 0)
  const source = audioCtx.createBufferSource()
  source.buffer = buffer
  source.connect(audioCtx.destination)
  source.start()
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChronos(backendWsUrl: string) {
  const [sceneState, setSceneState] = useState<SceneState | null>(null)
  const [scenePlan, setScenePlan] = useState<ScenePlan | null>(null)
  const [cutscene, setCutscene] = useState<CutsceneData | null>(null)
  const [status, setStatus] = useState('Connecting…')
  const [transcript, setTranscript] = useState('')

  const wsRef = useRef<WebSocket | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const sessionIdRef = useRef<string>(
    `session-${Math.random().toString(36).slice(2, 10)}`
  )

  // Connect WebSocket
  useEffect(() => {
    const sessionId = sessionIdRef.current
    const url = `${backendWsUrl}/ws/${sessionId}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setStatus('Connected')
    ws.onclose = () => setStatus('Disconnected')
    ws.onerror = () => setStatus('Connection error')

    ws.onmessage = (event: MessageEvent<string>) => {
      let msg: WSMessage
      try {
        msg = JSON.parse(event.data) as WSMessage
      } catch {
        return
      }

      switch (msg.type) {
        case 'scene_update':
          setSceneState(msg.payload as SceneState)
          break

        case 'scene_plan_update':
          setScenePlan(msg.payload as ScenePlan)
          setStatus('Ready')
          break

        case 'cutscene_start':
          setCutscene(msg.payload as CutsceneData)
          break

        case 'transcript': {
          const text = (msg.payload as { text: string }).text
          setTranscript(text)
          break
        }

        case 'audio_output': {
          const data = (msg.payload as { data: number[] }).data
          if (!audioCtxRef.current) {
            audioCtxRef.current = new AudioContext({ sampleRate: 24000 })
          }
          playPcmChunk(audioCtxRef.current, data)
          break
        }

        case 'status': {
          const payload = msg.payload as Record<string, unknown>
          if (payload?.scene_exited) {
            setScenePlan(null)
            setSceneState(null)
            setCutscene(null)
            setTranscript('')
            setStatus('Ready')
          } else {
            setStatus('Ready')
          }
          break
        }

        case 'error': {
          const detail = (msg.payload as { detail: string }).detail
          setStatus(`Error: ${detail}`)
          break
        }
      }
    }

    return () => {
      ws.close()
      audioCtxRef.current?.close().catch(() => undefined)
    }
  }, [backendWsUrl])

  // ---------------------------------------------------------------------------
  // Send helpers
  // ---------------------------------------------------------------------------

  const send = useCallback((msg: WSMessage) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg))
    }
  }, [])

  const sendText = useCallback(
    (text: string) => {
      send({ type: 'text_input', payload: { text } })
    },
    [send]
  )

  const sendAudio = useCallback(
    (pcm: Uint8Array) => {
      send({ type: 'audio_chunk', payload: { data: Array.from(pcm) } })
    },
    [send]
  )

  const sendSceneRequest = useCallback(
    (prompt: string) => {
      send({ type: 'scene_request', payload: { prompt } })
    },
    [send]
  )

  /** Trigger NPC interaction: server will respond with cutscene_start */
  const sendNpcInteract = useCallback(
    (npcId: string) => {
      send({ type: 'npc_interact', payload: { npc_id: npcId } })
    },
    [send]
  )

  /** Leave NPC interaction: server restores general Live session */
  const sendNpcLeave = useCallback(() => {
    send({ type: 'npc_leave' })
    setCutscene(null)
  }, [send])

  /** Exit the current scene entirely: server clears scene state */
  const sendSceneExit = useCallback(() => {
    send({ type: 'scene_exit' })
  }, [send])

  return {
    sceneState,
    scenePlan,
    cutscene,
    status,
    transcript,
    sendText,
    sendAudio,
    sendSceneRequest,
    sendNpcInteract,
    sendNpcLeave,
    sendSceneExit,
  }
}
