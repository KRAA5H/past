/**
 * Scene.tsx — Three.js / R3F room with dynamically placed NPCs and objects.
 *
 * NPCs are represented as simple capsule meshes until real GLTF assets are
 * available.  Objects are rendered as boxes with a label.
 */
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import {
  Environment,
  OrbitControls,
  Text,
  Html,
} from '@react-three/drei'
import * as THREE from 'three'
import type { SceneState, NPCBase, SceneObjectBase } from './useChronos'

// ---------------------------------------------------------------------------
// NPC mesh
// ---------------------------------------------------------------------------

interface NPCProps {
  npc: NPCBase
}

function NPCMesh({ npc }: NPCProps) {
  const meshRef = useRef<THREE.Mesh>(null)

  // Simple idle bob animation
  useFrame(({ clock }) => {
    if (meshRef.current && npc.action === 'idle') {
      meshRef.current.position.y =
        npc.position[1] + Math.sin(clock.getElapsedTime() * 1.5) * 0.04
    }
  })

  const moodColor: Record<string, string> = {
    neutral: '#94a3b8',
    happy: '#fbbf24',
    sad: '#60a5fa',
    angry: '#f87171',
    fearful: '#a78bfa',
    surprised: '#34d399',
  }

  const color = moodColor[npc.mood] ?? '#94a3b8'

  return (
    <group position={npc.position as [number, number, number]}>
      {/* Body */}
      <mesh ref={meshRef}>
        <capsuleGeometry args={[0.25, 0.8, 8, 16]} />
        <meshStandardMaterial color={color} />
      </mesh>
      {/* Name label */}
      <Text
        position={[0, 1.1, 0]}
        fontSize={0.18}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.02}
        outlineColor="#000000"
      >
        {npc.name}
      </Text>
      {/* Dialogue bubble */}
      {npc.dialogue && (
        <Html position={[0, 1.5, 0]} center distanceFactor={6}>
          <div
            style={{
              background: 'rgba(255,255,255,0.9)',
              color: '#1e293b',
              padding: '4px 8px',
              borderRadius: 8,
              fontSize: 11,
              maxWidth: 160,
              textAlign: 'center',
              pointerEvents: 'none',
            }}
          >
            {npc.dialogue}
          </div>
        </Html>
      )}
    </group>
  )
}

// ---------------------------------------------------------------------------
// Scene object mesh
// ---------------------------------------------------------------------------

interface SceneObjectProps {
  obj: SceneObjectBase
}

function SceneObjectMesh({ obj }: SceneObjectProps) {
  return (
    <group
      position={obj.position as [number, number, number]}
      rotation={obj.rotation as [number, number, number]}
      scale={obj.scale as [number, number, number]}
    >
      <mesh>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#78716c" wireframe />
      </mesh>
      <Text
        position={[0, 0.7, 0]}
        fontSize={0.15}
        color="#e2e8f0"
        anchorX="center"
        anchorY="middle"
      >
        {obj.asset}
      </Text>
    </group>
  )
}

// ---------------------------------------------------------------------------
// Ground plane
// ---------------------------------------------------------------------------

function Ground() {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[40, 40]} />
      <meshStandardMaterial color="#4a5568" roughness={1} />
    </mesh>
  )
}

// ---------------------------------------------------------------------------
// Main Scene
// ---------------------------------------------------------------------------

interface SceneProps {
  state: SceneState | null
}

export function Scene({ state }: SceneProps) {
  const lighting = state?.lighting ?? 'day'

  const envPreset: 'sunset' | 'dawn' | 'night' | 'warehouse' | 'forest' | 'apartment' | 'city' | 'studio' | 'park' | 'lobby' =
    lighting === 'night'
      ? 'night'
      : lighting === 'dawn' || lighting === 'dusk'
      ? 'dawn'
      : 'city'

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={lighting === 'night' ? 0.2 : 0.6} />
      <directionalLight
        position={[10, 20, 10]}
        intensity={lighting === 'night' ? 0.3 : 1.2}
        castShadow
      />
      <Environment preset={envPreset} background blur={0.6} />

      {/* Controls */}
      <OrbitControls
        makeDefault
        minDistance={2}
        maxDistance={30}
        maxPolarAngle={Math.PI / 2.1}
      />

      {/* Ground */}
      <Ground />

      {/* NPCs */}
      {state?.npcs.map((npc) => (
        <NPCMesh key={npc.npc_id} npc={npc} />
      ))}

      {/* Objects */}
      {state?.objects.map((obj) => (
        <SceneObjectMesh key={obj.object_id} obj={obj} />
      ))}

      {/* Empty state hint */}
      {!state && (
        <Text
          position={[0, 1, 0]}
          fontSize={0.4}
          color="#64748b"
          anchorX="center"
          anchorY="middle"
        >
          Describe a historical scene to begin
        </Text>
      )}
    </>
  )
}
