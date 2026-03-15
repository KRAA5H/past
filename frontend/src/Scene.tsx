/**
 * Scene.tsx — Three.js / R3F room with dynamically placed NPCs and objects.
 *
 * Characters are rendered with GLTF models when available, falling back to
 * capsule meshes.  Environment maps use custom EXR files for realistic IBL.
 *
 * When a ScenePlan is available, renders the structured scene instead.
 */
import { Suspense, useRef, useMemo, Component, type ReactNode } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import {
  ContactShadows,
  Environment,
  OrbitControls,
  Sky,
  Text,
  Html,
  useGLTF,
} from '@react-three/drei'
import {
  EffectComposer,
  Bloom,
  Vignette,
  DepthOfField,
  Noise,
} from '@react-three/postprocessing'
import * as THREE from 'three'
import type { SceneState, NPCBase, SceneObjectBase, ScenePlan, ScenePlanLight, ScenePlanProp, ScenePlanCharacter } from './useChronos'
import { toTuple3 } from './useChronos'

// ---------------------------------------------------------------------------
// Error boundary — renders fallback children when a subtree throws (e.g.
// missing GLTF asset triggers a network error inside useGLTF).
// ---------------------------------------------------------------------------

interface ErrorBoundaryProps {
  fallback: ReactNode
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

class ModelErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}

// ---------------------------------------------------------------------------
// Character archetype → GLB model path mapping
// ---------------------------------------------------------------------------

// Five distinct GLB models are available; archetypes without a unique model
// share the closest visual match until dedicated assets are added.
const ARCHETYPE_MODEL_MAP: Record<string, string> = {
  formal_male: '/models/cowboy.glb',
  formal_female: '/models/cowgirl.glb',
  military_male: '/models/fighter_male.glb',
  military_female: '/models/fighter_female.glb',
  laborer: '/models/warrior.glb',
  scientist: '/models/cowboy.glb',
  civilian: '/models/cowgirl.glb',
}

// ---------------------------------------------------------------------------
// Skybox / time-of-day → EXR environment map path mapping
// ---------------------------------------------------------------------------

const SKYBOX_EXR_MAP: Record<string, string> = {
  dawn: '/assets/kiara_1_dawn_4k.exr',
  sunrise: '/assets/kiara_1_dawn_4k.exr',
  night: '/assets/dikhololo_night_4k.exr',
  night_stars: '/assets/dikhololo_night_4k.exr',
  sunset: '/assets/canary_wharf_4k.exr',
  dusk: '/assets/canary_wharf_4k.exr',
}

const DEFAULT_EXR = '/assets/canary_wharf_4k.exr'

// ---------------------------------------------------------------------------
// Scene / prop asset slug → GLB path mapping
// ---------------------------------------------------------------------------

const SCENE_ASSET_MAP: Record<string, string> = {
  abandoned_mansion_bedroom: '/assets/scenes/abandoned_mansion_bedroom/scene.glb',
  armor_set: '/assets/scenes/armor_set/scene.glb',
  british_pub: '/assets/scenes/british_pub/scene.glb',
  furniture_a_models_from_fps_creator_classic: '/assets/scenes/furniture_a_models_from_fps_creator_classic/scene.glb',
  gameready_colt_python_revolver: '/assets/scenes/gameready_colt_python_revolver/scene.glb',
  garden_table: '/assets/scenes/garden_table/scene.glb',
  human_models_set_malefemale_rigged: '/assets/scenes/human_models_set_-_malefemale_rigged/scene.glb',
  knight_includes_file_for_3d_printing: '/assets/scenes/knight_-_includes_file_for_3d_printing/scene.glb',
  medieval_tavern: '/assets/scenes/medieval_tavern/scene.glb',
  old_bar: '/assets/scenes/old_bar/scene.glb',
  old_town: '/assets/scenes/old_town/scene.glb',
  restaurant_in_the_evening: '/assets/scenes/restaurant_in_the_evening/scene.glb',
  ruins_of_hore_abbey: '/assets/scenes/ruins_of_hore_abbey/scene.glb',
  stylized_medieval_castle_room: '/assets/scenes/stylized_medieval_castle_room/scene.glb',
  table_and_chairs_low_poly: '/assets/scenes/table_and_chairs_-_low_poly/scene.glb',
}

// ---------------------------------------------------------------------------
// Material property lookup by material_type
// ---------------------------------------------------------------------------

interface PhysicalMaterialProps {
  roughness: number
  metalness: number
  clearcoat: number
  sheen: number
  transmission: number
}

const MATERIAL_PROPERTIES: Record<string, PhysicalMaterialProps> = {
  wood:    { roughness: 0.8, metalness: 0.0, clearcoat: 0.1, sheen: 0.0, transmission: 0.0 },
  metal:   { roughness: 0.3, metalness: 0.9, clearcoat: 0.2, sheen: 0.0, transmission: 0.0 },
  fabric:  { roughness: 0.9, metalness: 0.0, clearcoat: 0.0, sheen: 0.8, transmission: 0.0 },
  glass:   { roughness: 0.05, metalness: 0.0, clearcoat: 1.0, sheen: 0.0, transmission: 0.8 },
  stone:   { roughness: 0.9, metalness: 0.0, clearcoat: 0.0, sheen: 0.0, transmission: 0.0 },
  plastic: { roughness: 0.4, metalness: 0.0, clearcoat: 0.5, sheen: 0.0, transmission: 0.0 },
  paper:   { roughness: 0.95, metalness: 0.0, clearcoat: 0.0, sheen: 0.1, transmission: 0.0 },
  leather: { roughness: 0.7, metalness: 0.0, clearcoat: 0.15, sheen: 0.3, transmission: 0.0 },
  ceramic: { roughness: 0.3, metalness: 0.0, clearcoat: 0.6, sheen: 0.0, transmission: 0.0 },
}

// ---------------------------------------------------------------------------
// Environment preset mapping
// ---------------------------------------------------------------------------

type EnvPreset = 'sunset' | 'dawn' | 'night' | 'warehouse' | 'forest' | 'apartment' | 'city' | 'studio' | 'park' | 'lobby'

function getEnvPreset(architectureStyle?: string, timeOfDay?: string): EnvPreset {
  // Time-of-day takes priority for outdoor feel
  if (timeOfDay === 'dawn' || timeOfDay === 'sunrise') return 'dawn'
  if (timeOfDay === 'dusk' || timeOfDay === 'sunset') return 'sunset'
  if (timeOfDay === 'night') return 'night'

  // Architecture style fallback
  switch (architectureStyle) {
    case 'victorian':
    case 'colonial_american':
      return 'apartment'
    case 'ancient_roman':
    case 'ancient_greek':
      return 'park'
    case 'medieval_european':
      return 'forest'
    case 'ww1_trench':
    case 'ww2_bunker':
      return 'warehouse'
    case 'space_age':
    case 'mid_century_modern':
      return 'studio'
    case 'contemporary':
    default:
      return 'city'
  }
}

// ---------------------------------------------------------------------------
// Resolve the best EXR environment file for the scene, or null to use preset
// ---------------------------------------------------------------------------

function getEnvFile(timeOfDay?: string, skyboxHint?: string): string | null {
  if (skyboxHint && skyboxHint !== 'none' && SKYBOX_EXR_MAP[skyboxHint]) {
    return SKYBOX_EXR_MAP[skyboxHint]
  }
  if (timeOfDay && SKYBOX_EXR_MAP[timeOfDay]) {
    return SKYBOX_EXR_MAP[timeOfDay]
  }
  return DEFAULT_EXR
}

function getSceneBackgroundColor(atmosphere?: string, timeOfDay?: string): string {
  // Darker backgrounds for nighttime / tense scenes
  if (timeOfDay === 'night') return '#0a0a1a'
  if (timeOfDay === 'dawn' || timeOfDay === 'sunrise') return '#2a1a30'
  if (timeOfDay === 'dusk' || timeOfDay === 'sunset') return '#3a1a10'

  switch (atmosphere) {
    case 'tense':
    case 'ominous':
      return '#1a1a2e'
    case 'solemn':
      return '#2a2a3e'
    case 'chaotic':
      return '#3a2020'
    case 'triumphant':
    case 'celebratory':
      return '#2e2e1a'
    case 'quiet':
      return '#2e3a2e'
    default:
      return '#1e293b'
  }
}

// ---------------------------------------------------------------------------
// Degree to radian conversion helper
// ---------------------------------------------------------------------------

function degToRad(degrees: number): number {
  return degrees * (Math.PI / 180)
}

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
        <meshPhysicalMaterial color={color} roughness={0.7} metalness={0.0} />
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
        <meshPhysicalMaterial color="#78716c" wireframe />
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
      <meshPhysicalMaterial color="#4a5568" roughness={1} />
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
        <meshPhysicalMaterial color="#4a5568" roughness={1} />
      </mesh>
      {/* Back wall */}
      <mesh position={[0, height / 2, -depth / 2]} receiveShadow>
        <planeGeometry args={[width, height]} />
        <meshPhysicalMaterial color="#6b7280" side={THREE.DoubleSide} />
      </mesh>
      {/* Left wall */}
      <mesh position={[-width / 2, height / 2, 0]} rotation={[0, Math.PI / 2, 0]} receiveShadow>
        <planeGeometry args={[depth, height]} />
        <meshPhysicalMaterial color="#6b7280" side={THREE.DoubleSide} />
      </mesh>
      {/* Right wall */}
      <mesh position={[width / 2, height / 2, 0]} rotation={[0, -Math.PI / 2, 0]} receiveShadow>
        <planeGeometry args={[depth, height]} />
        <meshPhysicalMaterial color="#6b7280" side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// ---------------------------------------------------------------------------
// ScenePlan — Light
// ---------------------------------------------------------------------------

function PlanLight({ light }: { light: ScenePlanLight }) {
  const pos = toTuple3(light.position)
  const decay = light.decay ?? 2
  const castShadow = light.cast_shadow ?? true

  switch (light.type) {
    case 'point':
      return <pointLight position={pos} color={light.color} intensity={light.intensity} decay={decay} castShadow={castShadow} />
    case 'spot':
      return <spotLight position={pos} color={light.color} intensity={light.intensity} decay={decay} castShadow={castShadow} />
    case 'ambient':
      return <ambientLight color={light.color} intensity={light.intensity} />
    default:
      return <pointLight position={pos} color={light.color} intensity={light.intensity} decay={decay} castShadow={castShadow} />
  }
}

// ---------------------------------------------------------------------------
// ScenePlan — Prop (with optional glTF model)
// ---------------------------------------------------------------------------

function GLTFPropModel({ url }: { url: string }) {
  const { scene } = useGLTF(url)
  const cloned = useMemo(() => {
    const clone = scene.clone(true)
    clone.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        child.castShadow = true
        child.receiveShadow = true
      }
    })
    return clone
  }, [scene])
  // GLB_TO_SCENE_SCALE converts from typical cm-authored assets to metres.
  // Per-prop sizing is handled by the parent group's scale (from prop.scale).
  return <primitive object={cloned} scale={GLB_TO_SCENE_SCALE} />
}

function PlanProp({ prop }: { prop: ScenePlanProp }) {
  const pos = toTuple3(prop.position)
  const [w, h, d] = prop.dimensions
  const matColor = prop.material?.color ?? '#888888'

  // Look up physical material props from the material_type field
  const matType = prop.material_type ?? 'wood'
  const physicalProps = MATERIAL_PROPERTIES[matType] ?? MATERIAL_PROPERTIES.wood

  // Emissive properties
  const isEmissive = prop.emissive ?? false
  const emissiveColor = isEmissive ? (prop.emissive_color ?? '#ffffff') : undefined
  const emissiveIntensity = isEmissive ? (prop.emissive_intensity ?? 1.0) : 0

  // Scale and rotation from new fields
  const propScale = prop.scale ?? [1, 1, 1]
  const rotationY = degToRad(prop.rotation_y ?? 0)

  // Resolve optional glTF asset
  const gltfSlug = prop.gltf_asset ?? null
  const gltfUrl = gltfSlug ? SCENE_ASSET_MAP[gltfSlug] ?? null : null

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

  // Primitive fallback mesh — always available as a safety net
  const primitiveFallback = (
    <mesh castShadow receiveShadow>
      {geometry}
      <meshPhysicalMaterial
        color={matColor}
        roughness={physicalProps.roughness}
        metalness={physicalProps.metalness}
        clearcoat={physicalProps.clearcoat}
        sheen={physicalProps.sheen}
        transmission={physicalProps.transmission}
        emissive={emissiveColor}
        emissiveIntensity={emissiveIntensity}
      />
    </mesh>
  )

  return (
    <group position={pos} rotation={[0, rotationY, 0]} scale={propScale as [number, number, number]}>
      {gltfUrl ? (
        <ModelErrorBoundary fallback={primitiveFallback}>
          <Suspense fallback={primitiveFallback}>
            <GLTFPropModel url={gltfUrl} />
          </Suspense>
        </ModelErrorBoundary>
      ) : (
        primitiveFallback
      )}
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
// ScenePlan — Character with GLTF model loading
// ---------------------------------------------------------------------------

// GLB models are typically authored in centimetre scale; multiply by 0.01
// to convert to the scene's metre-based coordinate system.
const GLB_TO_SCENE_SCALE = 0.01

function GLTFCharacterModel({ url, meshScale }: { url: string; meshScale: number }) {
  const { scene } = useGLTF(url)
  const cloned = useMemo(() => {
    const clone = scene.clone(true)
    clone.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        child.castShadow = true
        child.receiveShadow = true
      }
    })
    return clone
  }, [scene])
  return <primitive object={cloned} scale={meshScale * GLB_TO_SCENE_SCALE} />
}

function CharacterCapsuleFallback({
  meshScale,
  color,
}: {
  meshScale: number
  color: string
}) {
  return (
    <mesh scale={[meshScale, meshScale, meshScale]} castShadow receiveShadow>
      <capsuleGeometry args={[0.25, 0.8, 8, 16]} />
      <meshPhysicalMaterial color={color} roughness={0.7} metalness={0.0} />
    </mesh>
  )
}

function PlanCharacter({ char }: { char: ScenePlanCharacter }) {
  const pos = toTuple3(char.position)
  const isPrimary = char.primary
  const meshScale = isPrimary ? 1.8 : 1.6
  const color = isPrimary ? '#4a90d9' : '#7a7a7a'

  const rotationY = degToRad(char.rotation_y ?? 0)

  const archetype = char.archetype ?? 'formal_male'
  const modelUrl = ARCHETYPE_MODEL_MAP[archetype]

  const fallback = (
    <CharacterCapsuleFallback meshScale={meshScale} color={color} />
  )

  return (
    <group
      position={pos}
      rotation={[0, rotationY, 0]}
      userData={{
        animation_hint: char.animation_hint ?? 'idle_standing',
        archetype,
      }}
    >
      {/* Character model: try GLTF, fall back to capsule */}
      {modelUrl ? (
        <ModelErrorBoundary fallback={fallback}>
          <Suspense fallback={fallback}>
            <GLTFCharacterModel url={modelUrl} meshScale={meshScale} />
          </Suspense>
        </ModelErrorBoundary>
      ) : (
        fallback
      )}
      {/* Name label */}
      <Text
        position={[0, meshScale * 0.7 + 0.3, 0]}
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
        position={[0, meshScale * 0.7 + 0.05, 0]}
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
          <meshPhysicalMaterial color="#4a90d9" emissive="#4a90d9" emissiveIntensity={0.8} />
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
  useFrame(() => {
    if (!hasSet.current) {
      camera.position.set(position[0], position[1], position[2])
      hasSet.current = true
    }
  })
  return null
}

// ---------------------------------------------------------------------------
// HDR Environment — tries EXR file, falls back to drei preset
// ---------------------------------------------------------------------------

function HDREnvironment({
  envFile,
  envPreset,
}: {
  envFile: string | null
  envPreset: EnvPreset
}) {
  if (envFile) {
    return (
      <ModelErrorBoundary fallback={<Environment preset={envPreset} />}>
        <Suspense fallback={<Environment preset={envPreset} />}>
          <Environment files={envFile} />
        </Suspense>
      </ModelErrorBoundary>
    )
  }
  return <Environment preset={envPreset} />
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
    // Derive scene mood variables from room fields
    const isIndoors = !(scenePlan.room.has_windows ?? false)
    const timeOfDay = scenePlan.room.time_of_day ?? 'unknown'
    const atmosphere = scenePlan.room.atmosphere ?? 'mundane'
    const architectureStyle = scenePlan.room.architecture_style ?? 'contemporary'
    const skyboxHint = scenePlan.skybox_hint ?? 'none'

    const envPreset = getEnvPreset(architectureStyle, timeOfDay)
    const envFile = getEnvFile(timeOfDay, skyboxHint)
    const bgColor = getSceneBackgroundColor(atmosphere, timeOfDay)

    // Determine if Sky should render
    const showSky = !isIndoors && skyboxHint !== 'none'

    // Fog settings based on indoor/outdoor
    const fogColor = scenePlan.room.fog.color
    const fogNear = isIndoors ? scenePlan.room.fog.near : scenePlan.room.fog.near * 1.5
    const fogFar = isIndoors ? scenePlan.room.fog.far : scenePlan.room.fog.far * 2

    // Bloom and vignette intensity based on atmosphere and indoor/outdoor
    const isTense = atmosphere === 'tense' || atmosphere === 'ominous'
    const bloomIntensity = isIndoors ? (isTense ? 1.2 : 0.6) : (isTense ? 0.5 : 0.3)
    const vignetteOffset = isIndoors ? (isTense ? 0.3 : 0.4) : 0.5
    const vignetteDarkness = isIndoors ? (isTense ? 0.7 : 0.4) : 0.2

    return (
      <>
        {/* Camera position from ScenePlan */}
        <CameraSetter position={toTuple3(scenePlan.camera_start)} />

        {/* Background colour */}
        <color attach="background" args={[bgColor]} />

        {/* Fog */}
        <fog attach="fog" args={[fogColor, fogNear, fogFar]} />

        {/* Image-based lighting — prefer EXR, fall back to preset */}
        <HDREnvironment envFile={envFile} envPreset={envPreset} />

        {/* Low ambient fill */}
        <ambientLight
          color={scenePlan.room.ambient_light_color ?? '#ffffff'}
          intensity={0.15}
        />

        {/* Shadow-casting directional light with high-res shadow map */}
        <directionalLight
          position={[8, 12, 5]}
          intensity={0.5}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
          shadow-bias={-0.0001}
          shadow-camera-left={-15}
          shadow-camera-right={15}
          shadow-camera-top={15}
          shadow-camera-bottom={-15}
        />

        {/* Contact shadows on the ground */}
        <ContactShadows
          position={[0, 0, 0]}
          opacity={0.6}
          scale={30}
          blur={2}
          far={10}
        />

        {/* Sky component (only for outdoor/windowed scenes with a skybox) */}
        {showSky && <Sky sunPosition={[100, 20, 100]} />}

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

        {/* Post-processing effects */}
        <EffectComposer>
          <Bloom
            intensity={bloomIntensity}
            luminanceThreshold={0.6}
            luminanceSmoothing={0.9}
          />
          <Vignette offset={vignetteOffset} darkness={vignetteDarkness} />
          <DepthOfField
            focusDistance={0.01}
            focalLength={0.05}
            bokehScale={1.5}
          />
          <Noise opacity={0.02} />
        </EffectComposer>
      </>
    )
  }

  // Fallback: existing SceneState rendering
  const lighting = state?.lighting ?? 'day'

  const envPreset: EnvPreset =
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
