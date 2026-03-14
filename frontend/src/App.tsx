import { useEffect, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Scene } from './Scene'
import { useChronos } from './useChronos'
import { AudioManager } from './AudioManager'

// ---------------------------------------------------------------------------
// App-level stage machine
//
//  idle        — prompt input overlay; user describes a historical idea
//  generating  — loading overlay while ScenePlan is being built
//  scene       — 3D scene rendered; press [E] to interact with primary NPC
//  cutscene    — intro narration overlay before NPC voice conversation
//  npc_chat    — live voice conversation with the NPC character
// ---------------------------------------------------------------------------

type AppStage = 'idle' | 'generating' | 'scene' | 'cutscene' | 'npc_chat'

// Shared overlay container style
const overlayBase: React.CSSProperties = {
  position: 'absolute',
  inset: 0,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'rgba(0,0,0,0.75)',
  color: '#fff',
  padding: '2rem',
  gap: '1.5rem',
  zIndex: 10,
}

export default function App() {
  const {
    scenePlan,
    cutscene,
    status,
    transcript,
    sendAudio,
    sendSceneRequest,
    sendNpcInteract,
    sendNpcLeave,
    sendSceneExit,
  } = useChronos(`ws://${window.location.hostname}:8000`)

  const [stage, setStage] = useState<AppStage>('idle')
  const [prompt, setPrompt] = useState('')
  const [recording, setRecording] = useState(false)
  const audioManagerRef = useRef<AudioManager | null>(null)

  // Wire AudioManager → sendAudio
  useEffect(() => {
    const am = new AudioManager((pcm) => sendAudio(pcm))
    audioManagerRef.current = am
    return () => am.stop()
  }, [sendAudio])

  // Advance stage when a ScenePlan arrives
  useEffect(() => {
    if (scenePlan) {
      setStage('scene')
    }
  }, [scenePlan])

  // Advance to cutscene when the server sends cutscene_start
  useEffect(() => {
    if (cutscene) {
      setStage('cutscene')
    }
  }, [cutscene])

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'e' || e.key === 'E') {
        // Press [E] in scene stage → interact with primary NPC
        if (stage === 'scene' && scenePlan) {
          const primary = scenePlan.characters.find((c) => c.primary)
          if (primary) {
            sendNpcInteract(primary.id)
          }
        }
      }
      if (e.key === 'Escape') {
        if (stage === 'npc_chat' || stage === 'cutscene') {
          // Leave NPC interaction
          handleLeaveNpc()
        } else if (stage === 'scene') {
          // Exit scene
          handleExitScene()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, scenePlan])

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return
    setStage('generating')
    sendSceneRequest(prompt.trim())
    setPrompt('')
  }

  const handleNpcInteract = (npcId: string) => {
    sendNpcInteract(npcId)
  }

  const handleCutsceneAdvance = () => {
    setStage('npc_chat')
  }

  const handleLeaveNpc = async () => {
    // Stop recording if active
    const am = audioManagerRef.current
    if (am && recording) {
      am.stop()
      setRecording(false)
    }
    sendNpcLeave()
    setStage('scene')
  }

  const handleExitScene = () => {
    sendSceneExit()
    setStage('idle')
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

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* 3-D canvas — always mounted so the scene can load in background */}
      <Canvas
        camera={{ position: [0, 2, 8], fov: 60 }}
        style={{ position: 'absolute', inset: 0 }}
      >
        <Scene
          plan={scenePlan}
          onNpcInteract={handleNpcInteract}
          interactive={stage === 'scene'}
        />
      </Canvas>

      {/* ── Stage: idle ──────────────────────────────────────────────── */}
      {stage === 'idle' && (
        <div style={overlayBase}>
          <h1 style={{ fontSize: '2rem', fontWeight: 700, textAlign: 'center' }}>
            Chronos
          </h1>
          <p style={{ opacity: 0.7, textAlign: 'center', maxWidth: 480 }}>
            Describe a historical moment and step into it.
          </p>
          <form
            onSubmit={handleSubmit}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', width: '100%', maxWidth: 480 }}
          >
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Apollo 11 Moon landing, Caesar's assassination…"
              style={{
                padding: '0.75rem 1rem',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.2)',
                background: 'rgba(255,255,255,0.1)',
                color: '#fff',
                fontSize: '1rem',
                outline: 'none',
              }}
            />
            <button
              type="submit"
              disabled={!prompt.trim()}
              style={{
                padding: '0.75rem',
                borderRadius: 8,
                border: 'none',
                background: '#4f46e5',
                color: '#fff',
                fontSize: '1rem',
                cursor: 'pointer',
                opacity: prompt.trim() ? 1 : 0.4,
              }}
            >
              Enter the Past
            </button>
          </form>
          <div style={{ fontSize: '0.75rem', opacity: 0.4 }}>{status}</div>
        </div>
      )}

      {/* ── Stage: generating ────────────────────────────────────────── */}
      {stage === 'generating' && (
        <div style={overlayBase}>
          <div style={{ fontSize: '2rem' }}>⏳</div>
          <p style={{ fontSize: '1.1rem' }}>Reconstructing the scene…</p>
          <p style={{ opacity: 0.5, fontSize: '0.85rem' }}>
            Gemini is building your historical moment
          </p>
        </div>
      )}

      {/* ── Stage: scene — HUD ───────────────────────────────────────── */}
      {stage === 'scene' && scenePlan && (
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            padding: '1rem',
            background: 'rgba(0,0,0,0.55)',
            color: '#fff',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.4rem',
          }}
        >
          <div style={{ fontWeight: 700, fontSize: '1rem' }}>
            {scenePlan.event_name}
          </div>
          <div style={{ fontSize: '0.8rem', opacity: 0.75 }}>
            {scenePlan.dramatic_moment}
          </div>
          {transcript && (
            <div style={{ fontSize: '0.8rem', opacity: 0.85, fontStyle: 'italic' }}>
              "{transcript}"
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem', flexWrap: 'wrap' }}>
            {scenePlan.characters.map((c) => (
              <button
                key={c.id}
                onClick={() => handleNpcInteract(c.id)}
                title={c.role}
                style={{
                  padding: '0.35rem 0.75rem',
                  borderRadius: 6,
                  border: '1px solid rgba(255,255,255,0.3)',
                  background: c.primary ? '#4f46e5' : 'rgba(255,255,255,0.1)',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                }}
              >
                {c.primary ? '[E] ' : ''}{c.interact_text}
              </button>
            ))}
            <button
              onClick={handleExitScene}
              style={{
                marginLeft: 'auto',
                padding: '0.35rem 0.75rem',
                borderRadius: 6,
                border: '1px solid rgba(255,100,100,0.4)',
                background: 'rgba(220,38,38,0.2)',
                color: '#fca5a5',
                cursor: 'pointer',
                fontSize: '0.8rem',
              }}
            >
              [Esc] Exit Scene
            </button>
          </div>
          <div style={{ fontSize: '0.7rem', opacity: 0.4 }}>
            Press [E] to interact with the primary character · [Esc] to exit
          </div>
        </div>
      )}

      {/* ── Stage: cutscene ──────────────────────────────────────────── */}
      {stage === 'cutscene' && cutscene && (
        <div style={overlayBase}>
          <div
            style={{
              background: 'rgba(0,0,0,0.6)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 12,
              padding: '2rem',
              maxWidth: 560,
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: '0.75rem', opacity: 0.5, marginBottom: '0.5rem', letterSpacing: '0.1em' }}>
              NOW SPEAKING WITH
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '1.25rem' }}>
              {cutscene.character_name}
            </div>
            <p style={{ fontSize: '1rem', lineHeight: 1.7, opacity: 0.9 }}>
              {cutscene.intro_narration}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              onClick={handleCutsceneAdvance}
              style={{
                padding: '0.6rem 1.5rem',
                borderRadius: 8,
                border: 'none',
                background: '#4f46e5',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '0.95rem',
              }}
            >
              Begin Conversation →
            </button>
            <button
              onClick={handleLeaveNpc}
              style={{
                padding: '0.6rem 1.5rem',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.2)',
                background: 'transparent',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '0.95rem',
              }}
            >
              [Esc] Back
            </button>
          </div>
        </div>
      )}

      {/* ── Stage: npc_chat ──────────────────────────────────────────── */}
      {stage === 'npc_chat' && (
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            padding: '1rem',
            background: 'rgba(0,0,0,0.7)',
            color: '#fff',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
          }}
        >
          {cutscene && (
            <div style={{ fontWeight: 600, fontSize: '0.9rem', opacity: 0.8 }}>
              Talking with {cutscene.character_name}
            </div>
          )}
          {transcript && (
            <div
              style={{
                fontSize: '0.9rem',
                fontStyle: 'italic',
                opacity: 0.9,
                padding: '0.5rem',
                background: 'rgba(255,255,255,0.07)',
                borderRadius: 6,
                minHeight: '2rem',
              }}
            >
              "{transcript}"
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              onClick={toggleRecording}
              style={{
                padding: '0.5rem 1.25rem',
                borderRadius: 8,
                border: 'none',
                background: recording ? '#dc2626' : '#059669',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '0.9rem',
                flex: 1,
              }}
            >
              {recording ? '⏹ Stop Speaking' : '🎙 Speak'}
            </button>
            <button
              onClick={handleLeaveNpc}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.2)',
                background: 'transparent',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '0.85rem',
              }}
            >
              [Esc] Leave
            </button>
          </div>
          <div style={{ fontSize: '0.7rem', opacity: 0.4 }}>
            Press [Esc] to end the conversation
          </div>
        </div>
      )}
    </div>
  )
}
