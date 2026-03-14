/**
 * Scene.tsx — Three.js / R3F room with dynamically placed NPCs and objects.
 *
 * NPCs are represented as simple capsule meshes until real GLTF assets are
 * available.  Objects are rendered as boxes with a label.
 *
 * When a ScenePlan is available, renders the structured scene instead.
 */
import { useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import {
  Environment,
  OrbitControls,
  Text,
  Html,
} from '@react-three/drei'
import * as THREE from 'three'
import type { SceneState, NPCBase, SceneObjectBase, ScenePlan, ScenePlanLight, ScenePlanProp, ScenePlanCharacter } from './useChronos'
import { toTuple3 } from './useChronos'

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
// ScenePlan — Room (floor + walls)
// ---------------------------------------------------------------------------

function PlanRoom({ room }: { room: ScenePlan['room'] }) {
  const { width, depth, height } = room
  return (
    <group>
      {/* Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width, depth]} />
        <meshStandardMaterial color="#4a5568" roughness={1} />
      </mesh>
      {/* Back wall */}
      <mesh position={[0, height / 2, -depth / 2]}>
        <planeGeometry args={[width, height]} />
        <meshStandardMaterial color="#6b7280" side={THREE.DoubleSide} />
      </mesh>
      {/* Left wall */}
      <mesh position={[-width / 2, height / 2, 0]} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[depth, height]} />
        <meshStandardMaterial color="#6b7280" side={THREE.DoubleSide} />
      </mesh>
      {/* Right wall */}
      <mesh position={[width / 2, height / 2, 0]} rotation={[0, -Math.PI / 2, 0]}>
        <planeGeometry args={[depth, height]} />
        <meshStandardMaterial color="#6b7280" side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// ---------------------------------------------------------------------------
// ScenePlan — Light
// ---------------------------------------------------------------------------

function PlanLight({ light }: { light: ScenePlanLight }) {
  const pos = toTuple3(light.position)
  switch (light.type) {
    case 'point':
      return <pointLight position={pos} color={light.color} intensity={light.intensity} />
    case 'spot':
      return <spotLight position={pos} color={light.color} intensity={light.intensity} castShadow />
    case 'ambient':
      return <ambientLight color={light.color} intensity={light.intensity} />
    default:
      return <pointLight position={pos} color={light.color} intensity={light.intensity} />
  }
}

// ---------------------------------------------------------------------------
// ScenePlan — Prop
// ---------------------------------------------------------------------------

function PlanProp({ prop }: { prop: ScenePlanProp }) {
  const pos = toTuple3(prop.position)
  const [w, h, d] = prop.dimensions
  const matColor = prop.material?.color ?? '#888888'
  const roughness = prop.material?.roughness ?? 0.5
  const emissive = prop.material?.emissive_color ?? undefined

  let geometry: React.ReactNode
  switch (prop.shape) {
    case 'sphere':
      geometry = <sphereGeometry args={[w / 2, 32, 32]} />
      break
    case 'cylinder':
      geometry = <cylinderGeometry args={[w / 2, w / 2, h, 32]} />
      break
    default: // box
      geometry = <boxGeometry args={[w, h, d]} />
  }

  return (
    <group position={pos}>
      <mesh>
        {geometry}
        <meshStandardMaterial color={matColor} roughness={roughness} emissive={emissive} />
      </mesh>
      <Html position={[0, h / 2 + 0.3, 0]} center distanceFactor={8}>
        <div
          style={{
            background: 'rgba(0,0,0,0.7)',
            color: '#e2e8f0',
            padding: '2px 6px',
            borderRadius: 4,
            fontSize: 11,
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
          }}
        >
          {prop.id}
        </div>
      </Html>
    </group>
  )
}

// ---------------------------------------------------------------------------
// ScenePlan — Character
// ---------------------------------------------------------------------------

function PlanCharacter({ char }: { char: ScenePlanCharacter }) {
  const pos = toTuple3(char.position)
  const isPrimary = char.primary
  const scale = isPrimary ? 1.8 : 1.6
  const color = isPrimary ? '#4a90d9' : '#7a7a7a'

  return (
    <group position={pos}>
      {/* Body */}
      <mesh scale={[scale, scale, scale]}>
        <capsuleGeometry args={[0.25, 0.8, 8, 16]} />
        <meshStandardMaterial color={color} />
      </mesh>
      {/* Name label */}
      <Text
        position={[0, scale * 0.7 + 0.3, 0]}
        fontSize={0.2}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.02}
        outlineColor="#000000"
      >
        {char.name}
      </Text>
      {/* Role label */}
      <Text
        position={[0, scale * 0.7 + 0.05, 0]}
        fontSize={0.12}
        color="#a0aec0"
        anchorX="center"
        anchorY="middle"
      >
        {char.role}
      </Text>
      {/* Emissive ring under primary character */}
      {isPrimary && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
          <torusGeometry args={[0.5, 0.05, 8, 32]} />
          <meshStandardMaterial color="#4a90d9" emissive="#4a90d9" emissiveIntensity={0.8} />
        </mesh>
      )}
    </group>
  )
}

// ---------------------------------------------------------------------------
// ScenePlan — Camera setter
// ---------------------------------------------------------------------------

function CameraSetter({ position }: { position: [number, number, number] }) {
  const { camera } = useThree()
  const hasSet = useRef(false)
  if (!hasSet.current) {
    camera.position.set(position[0], position[1], position[2])
    hasSet.current = true
  }
  return null
}

// ---------------------------------------------------------------------------
// Main Scene
// ---------------------------------------------------------------------------

interface SceneProps {
  state: SceneState | null
  scenePlan?: ScenePlan | null
}

export function Scene({ state, scenePlan }: SceneProps) {
  // When scenePlan is available, render the structured scene
  if (scenePlan) {
    return (
      <>
        {/* Camera position from ScenePlan */}
        <CameraSetter position={toTuple3(scenePlan.camera_start)} />

        {/* Room fog */}
        <fog
          attach="fog"
          args={[scenePlan.room.fog.color, scenePlan.room.fog.near, scenePlan.room.fog.far]}
        />

        {/* Room ambient color */}
        <ambientLight color={scenePlan.room.ambient_color} intensity={0.4} />

        {/* Lights from ScenePlan */}
        {scenePlan.lights.map((light, i) => (
          <PlanLight key={`light-${i}`} light={light} />
        ))}

        {/* Controls */}
        <OrbitControls
          makeDefault
          minDistance={2}
          maxDistance={30}
          maxPolarAngle={Math.PI / 2.1}
        />

        {/* Room geometry */}
        <PlanRoom room={scenePlan.room} />

        {/* Props */}
        {scenePlan.props.map((prop) => (
          <PlanProp key={prop.id} prop={prop} />
        ))}

        {/* Characters */}
        {scenePlan.characters.map((char) => (
          <PlanCharacter key={char.id} char={char} />
        ))}
      </>
    )
  }

  // Fallback: existing SceneState rendering
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
