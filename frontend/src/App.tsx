import { useEffect, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { Scene } from './Scene'
import { useChronos } from './useChronos'
import { AudioManager } from './AudioManager'

export default function App() {
  const { sceneState, scenePlan, status, transcript, sendAudio, sendSceneRequest } =
    useChronos(`ws://${window.location.hostname}:8000`)

  const [prompt, setPrompt] = useState('')
  const audioManagerRef = useRef<AudioManager | null>(null)
  const [recording, setRecording] = useState(false)
  const [showNarration, setShowNarration] = useState(false)
  const narrationTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Fade out narration after 8 seconds when scenePlan changes
  useEffect(() => {
    if (narrationTimer.current) clearTimeout(narrationTimer.current)
    if (scenePlan?.intro_narration) {
      setShowNarration(true)
      narrationTimer.current = setTimeout(() => setShowNarration(false), 8000)
    } else {
      setShowNarration(false)
    }
    return () => {
      if (narrationTimer.current) clearTimeout(narrationTimer.current)
    }
  }, [scenePlan?.intro_narration])

  // Wire AudioManager → sendAudio
  useEffect(() => {
    const am = new AudioManager((pcm) => sendAudio(pcm))
    audioManagerRef.current = am
    return () => am.stop()
  }, [sendAudio])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return
    sendSceneRequest(prompt.trim())
    setPrompt('')
  }

  const toggleRecording = async () => {
    const am = audioManagerRef.current
    if (!am) return
    if (recording) {
      am.stop()
      setRecording(false)
    } else {
      await am.start()
      setRecording(true)
    }
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* 3-D canvas */}
      <Canvas
        shadows="soft"
        camera={{ position: [0, 2, 8], fov: 60 }}
        style={{ position: 'absolute', inset: 0 }}
        gl={{
          antialias: true,
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.2,
        }}
      >
        <Scene state={sceneState} scenePlan={scenePlan} />
      </Canvas>

      {/* Narration overlay */}
      {showNarration && scenePlan?.intro_narration && (
        <div
          style={{
            position: 'absolute',
            bottom: '5rem',
            left: '50%',
            transform: 'translateX(-50%)',
            maxWidth: '600px',
            width: '90%',
            padding: '0.75rem 1.25rem',
            background: 'rgba(0,0,0,0.75)',
            color: '#e2e8f0',
            borderRadius: 8,
            fontSize: '0.95rem',
            lineHeight: 1.5,
            textAlign: 'center',
            pointerEvents: 'none',
            transition: 'opacity 1s ease-out',
          }}
        >
          {scenePlan.intro_narration}
        </div>
      )}

      {/* HUD overlay */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          padding: '1rem',
          background: 'rgba(0,0,0,0.6)',
          color: '#fff',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
        }}
      >
        {/* Status + transcript */}
        <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>
          {status} {transcript && `— "${transcript}"`}
        </div>

        {/* Prompt input */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe a historical scene…"
            style={{
              flex: 1,
              padding: '0.5rem 0.75rem',
              borderRadius: 6,
              border: 'none',
              background: 'rgba(255,255,255,0.15)',
              color: '#fff',
              outline: 'none',
            }}
          />
          <button
            type="submit"
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 6,
              border: 'none',
              background: '#4f46e5',
              color: '#fff',
              cursor: 'pointer',
            }}
          >
            Generate
          </button>
          <button
            type="button"
            onClick={toggleRecording}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 6,
              border: 'none',
              background: recording ? '#dc2626' : '#059669',
              color: '#fff',
              cursor: 'pointer',
            }}
          >
            {recording ? '⏹ Stop' : '🎙 Speak'}
          </button>
        </form>

        {/* Scene description */}
        {sceneState && (
          <div style={{ fontSize: '0.8rem', opacity: 0.85 }}>
            {sceneState.description}
          </div>
        )}
      </div>
    </div>
  )
}
