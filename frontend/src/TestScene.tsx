// Temporary test file — delete when done
// Restore main.tsx to render <App /> when finished
import * as THREE from 'three'
import { useLayoutEffect, useRef, useState } from 'react'
import { Canvas, applyProps, useFrame } from '@react-three/fiber'
import { PerformanceMonitor, AccumulativeShadows, RandomizedLight, Environment, Lightformer, Float, useGLTF } from '@react-three/drei'

export function App() {
  const [degraded, degrade] = useState(false)
  return (
    <Canvas shadows camera={{ position: [0, 1.5, 4], fov: 30 }}>
      <spotLight position={[0, 15, 0]} angle={0.3} penumbra={1} castShadow intensity={2} shadow-bias={-0.0001} />
      <ambientLight intensity={0.5} />
      <Character scale={0.01} position={[0, 0, 0]} />
      <AccumulativeShadows position={[0, -0.001, 0]} frames={100} alphaTest={0.9} scale={6}>
        <RandomizedLight amount={8} radius={10} ambient={0.5} position={[1, 5, -1]} />
      </AccumulativeShadows>
      <PerformanceMonitor onDecline={() => degrade(true)} />
      <Environment frames={degraded ? 1 : Infinity} resolution={256} background blur={1}>
        <Lightformers />
      </Environment>
      <CameraRig />
    </Canvas>
  )
}

export default App

function Character(props: JSX.IntrinsicElements['group']) {
  const { scene, nodes, materials } = useGLTF('/assets/Cowboy.glb')
  useLayoutEffect(() => {
    Object.values(nodes).forEach((node: any) => {
      if (node.isMesh) {
        node.castShadow = true
        node.receiveShadow = true
      }
    })
    Object.values(materials).forEach((mat: any) => {
      applyProps(mat, { envMapIntensity: 2 })
    })
  }, [nodes, materials])
  return <primitive object={scene} {...props} />
}

function CameraRig({ v = new THREE.Vector3() }) {
  return useFrame((state) => {
    const t = state.clock.elapsedTime
    state.camera.position.lerp(v.set(Math.sin(t / 5) * 2, 1.5, 3 + Math.cos(t / 5) * 0.5), 0.05)
    state.camera.lookAt(0, 0.8, 0)
  })
}

function Lightformers({ positions = [2, 0, 2, 0, 2, 0, 2, 0] }) {
  const group = useRef<THREE.Group>(null!)
  useFrame((_, delta) => {
    group.current.position.z += delta * 10
    if (group.current.position.z > 20) group.current.position.z = -60
  })
  return (
    <>
      {/* Ceiling */}
      <Lightformer intensity={0.75} rotation-x={Math.PI / 2} position={[0, 5, -9]} scale={[10, 10, 1]} />
      <group rotation={[0, 0.5, 0]}>
        <group ref={group}>
          {positions.map((x, i) => (
            <Lightformer key={i} form="circle" intensity={2} rotation={[Math.PI / 2, 0, 0]} position={[x, 4, i * 4]} scale={[3, 1, 1]} />
          ))}
        </group>
      </group>
      {/* Sides */}
      <Lightformer intensity={4} rotation-y={Math.PI / 2} position={[-5, 1, -1]} scale={[20, 0.1, 1]} />
      <Lightformer rotation-y={Math.PI / 2} position={[-5, -1, -1]} scale={[20, 0.5, 1]} />
      <Lightformer rotation-y={-Math.PI / 2} position={[10, 1, 0]} scale={[20, 1, 1]} />
      {/* Accent */}
      <Float speed={5} floatIntensity={2} rotationIntensity={2}>
        <Lightformer form="ring" color="red" intensity={1} scale={10} position={[-15, 4, -18]} target={[0, 0, 0]} />
      </Float>
      {/* Background */}
      <mesh scale={100}>
        <sphereGeometry args={[1, 64, 64]} />
        <meshBasicMaterial color="#444" side={THREE.BackSide} />
      </mesh>
    </>
  )
}
