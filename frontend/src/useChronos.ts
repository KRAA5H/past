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
      send({ type: 'scene_request', payload: { prompt } })
    },
    [send]
  )

  return { sceneState, status, transcript, sendText, sendAudio, sendSceneRequest }
}
