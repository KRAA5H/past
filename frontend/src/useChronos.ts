/**
 * useChronos.ts — React hook that manages the WebSocket connection to the
 * Chronos backend, scene state, and audio playback of Gemini Live responses.
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
// ScenePlan types (mirror backend structured models)
// ---------------------------------------------------------------------------

type Vec3Input = { x: number; y: number; z: number } | [number, number, number]

export function toTuple3(v: Vec3Input): [number, number, number] {
  if (Array.isArray(v)) return [v[0], v[1], v[2]]
  return [v.x, v.y, v.z]
}

export interface ScenePlanFog {
  color: string
  near: number
  far: number
}

export interface ScenePlanRoom {
  width: number
  depth: number
  height: number
  fog: ScenePlanFog
  ambient_color: string
  architecture_style?: string
  time_of_day?: string
  atmosphere?: string
  ceiling_material?: string
  has_windows?: boolean
  ambient_light_color?: string
}

export interface ScenePlanLight {
  type: 'point' | 'spot' | 'ambient'
  position: Vec3Input
  color: string
  intensity: number
  decay?: number
  cast_shadow?: boolean
  source_label?: string
}

export interface ScenePlanMaterial {
  color: string
  roughness: number
  emissive_color?: string | null
}

export interface ScenePlanProp {
  id: string
  shape: 'box' | 'sphere' | 'cylinder'
  dimensions: [number, number, number]
  position: Vec3Input
  material: ScenePlanMaterial
  interactable: boolean
  material_type?: string
  scale?: [number, number, number]
  rotation_y?: number
  emissive?: boolean
  emissive_color?: string
  emissive_intensity?: number
  gltf_asset?: string | null
}

export interface ScenePlanCharacter {
  id: string
  name: string
  role: string
  position: Vec3Input
  primary: boolean
  persona_summary: string
  rotation_y?: number
  animation_hint?: string
  archetype?: string
}

export interface ScenePlan {
  scene_id: string
  event_name: string
  dramatic_moment: string
  room: ScenePlanRoom
  lights: ScenePlanLight[]
  props: ScenePlanProp[]
  characters: ScenePlanCharacter[]
  ambient_sounds: string[]
  intro_narration: string
  camera_start: Vec3Input
  skybox_hint?: string
}

type WSMessageType =
  | 'audio_chunk'
  | 'text_input'
  | 'scene_request'
  | 'scene_update'
  | 'audio_output'
  | 'transcript'
  | 'error'
  | 'status'

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

        case 'status':
          setStatus('Ready')
          break

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
      // Keep the existing WebSocket scene_request
      send({ type: 'scene_request', payload: { prompt } })

      // Also fire a parallel POST to the structured ScenePlan endpoint
      const httpBase = backendWsUrl.replace(/^ws/, 'http')
      fetch(`${httpBase}/api/scene/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      })
        .then((res) => {
          if (!res.ok) throw new Error(`ScenePlan fetch failed: ${res.status}`)
          return res.json() as Promise<ScenePlan>
        })
        .then((plan) => setScenePlan(plan))
        .catch((err) => console.error('[useChronos] ScenePlan error:', err))
    },
    [send, backendWsUrl]
  )

  return { sceneState, scenePlan, status, transcript, sendText, sendAudio, sendSceneRequest }
}
