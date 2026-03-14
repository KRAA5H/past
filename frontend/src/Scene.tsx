/**
 * Scene.tsx — Three.js / R3F room rendering a ScenePlan.
 *
 * Characters are rendered as capsule meshes until real GLTF assets are
 * available. Props are rendered as box/sphere/cylinder primitives using the
 * shape, dimensions, and material from the ScenePlan.
 *
 * When `interactive` is true the primary character shows an [E] prompt.
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
import type { ScenePlan, Character, Prop } from './useChronos'

// ---------------------------------------------------------------------------
// Character mesh
// ---------------------------------------------------------------------------

interface CharacterMeshProps {
  character: Character
  interactive: boolean
  onInteract?: (id: string) => void
}

function CharacterMesh({ character, interactive, onInteract }: CharacterMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null)

  // Simple idle bob
  useFrame(({ clock }) => {
    if (meshRef.current) {
      meshRef.current.position.y =
        character.position.y + Math.sin(clock.getElapsedTime() * 1.5) * 0.04
    }
  })

  const bodyColor = character.primary ? '#818cf8' : '#94a3b8'

  return (
    <group
      position={[character.position.x, character.position.y, character.position.z]}
    >
      {/* Body */}
      <mesh ref={meshRef}>
        <capsuleGeometry args={[0.25, 0.8, 8, 16]} />
        <meshStandardMaterial color={bodyColor} />
      </mesh>
      {/* Name label */}
      <Text
        position={[0, 1.3, 0]}
        fontSize={0.18}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.02}
        outlineColor="#000000"
      >
        {character.name}
      </Text>
      {/* Interaction prompt — shown only when the scene is explorable */}
      {interactive && (
        <Html position={[0, 1.75, 0]} center distanceFactor={6}>
          <div
            onClick={() => onInteract?.(character.id)}
            style={{
              background: character.primary
                ? 'rgba(79,70,229,0.9)'
                : 'rgba(0,0,0,0.7)',
              color: '#fff',
              padding: '3px 8px',
              borderRadius: 6,
              fontSize: 11,
              whiteSpace: 'nowrap',
              cursor: 'pointer',
              userSelect: 'none',
              border: '1px solid rgba(255,255,255,0.25)',
            }}
          >
            {character.primary ? '[E] ' : ''}{character.interact_text}
          </div>
        </Html>
      )}
    </group>
  )
}

// ---------------------------------------------------------------------------
// Prop mesh (box / sphere / cylinder primitives)
// ---------------------------------------------------------------------------

interface PropMeshProps {
  prop: Prop
}

function PropMesh({ prop }: PropMeshProps) {
  const [w, h, d] = prop.dimensions

  const geometry =
    prop.shape === 'sphere' ? (
      <sphereGeometry args={[w / 2, 16, 16]} />
    ) : prop.shape === 'cylinder' ? (
      <cylinderGeometry args={[w / 2, w / 2, h, 16]} />
    ) : (
      <boxGeometry args={[w, h, d]} />
    )

  return (
    <group
      position={[prop.position.x, prop.position.y, prop.position.z]}
    >
      <mesh>
        {geometry}
        <meshStandardMaterial
          color={prop.material.color}
          roughness={prop.material.roughness}
          emissive={prop.material.emissive_color ?? '#000000'}
        />
      </mesh>
      {prop.interactable && prop.interact_text && (
        <Text
          position={[0, h / 2 + 0.2, 0]}
          fontSize={0.13}
          color="#e2e8f0"
          anchorX="center"
          anchorY="middle"
        >
          {prop.interact_text}
        </Text>
      )}
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
  plan: ScenePlan | null
  onNpcInteract?: (npcId: string) => void
  interactive?: boolean
}

export function Scene({ plan, onNpcInteract, interactive = false }: SceneProps) {
  // Pick a sky environment based on the room's ambient colour darkness
  const ambientBrightness = plan
    ? parseInt(plan.room.ambient_color.slice(1, 3), 16)
    : 128
  const envPreset: 'sunset' | 'dawn' | 'night' | 'warehouse' | 'city' =
    ambientBrightness < 40 ? 'night' : ambientBrightness < 80 ? 'dawn' : 'city'

  return (
    <>
      {/* Scene lights from plan, or defaults */}
      {plan ? (
        plan.lights.map((light, i) => {
          if (light.type === 'ambient') {
            return (
              <ambientLight key={i} color={light.color} intensity={light.intensity} />
            )
          }
          if (light.type === 'spot') {
            return (
              <spotLight
                key={i}
                position={[light.position.x, light.position.y, light.position.z]}
                color={light.color}
                intensity={light.intensity}
                castShadow
              />
            )
          }
          return (
            <pointLight
              key={i}
              position={[light.position.x, light.position.y, light.position.z]}
              color={light.color}
              intensity={light.intensity}
            />
          )
        })
      ) : (
        <>
          <ambientLight intensity={0.6} />
          <directionalLight position={[10, 20, 10]} intensity={1.2} castShadow />
        </>
      )}

      {/* Environment */}
      <Environment preset={envPreset} background blur={0.6} />

      {/* Orbit controls */}
      <OrbitControls
        makeDefault
        minDistance={2}
        maxDistance={30}
        maxPolarAngle={Math.PI / 2.1}
      />

      {/* Ground */}
      <Ground />

      {/* Props */}
      {plan?.props.map((prop) => (
        <PropMesh key={prop.id} prop={prop} />
      ))}

      {/* Characters */}
      {plan?.characters.map((character) => (
        <CharacterMesh
          key={character.id}
          character={character}
          interactive={interactive}
          onInteract={onNpcInteract}
        />
      ))}

      {/* Empty-state hint */}
      {!plan && (
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
