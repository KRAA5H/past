# Rendering glTF Assets with React Three Fiber (R3F)

This guide provides context and instructions for implementing, visualizing, and rendering `.gltf` / `.glb` assets using React Three Fiber (`@react-three/fiber`) and Drei (`@react-three/drei`) within the `test` sandbox environment.

---

## 1. Prerequisites & Dependencies

Before rendering, ensure the required dependencies are installed in the `test` sandbox:

```bash
cd test
npm install three @react-three/fiber @react-three/drei
```

---

## 2. Asset Preparation

1. Place your `.gltf` or `.glb` files and their associated textures in the `public/` directory (e.g., inside `public/free_porsche_911_carrera_4s/`).
2. Optionally, use `gltfjsx` to auto-generate a typed React component from your model — this makes it easier to manipulate individual meshes and materials:
   ```bash
   npx gltfjsx public/model.gltf -o src/Model.jsx
   ```

---

## 3. Basic glTF Loading Implementation

Use the `useGLTF` hook from `@react-three/drei` to load and display a model without generating a component.

### `src/Model.js`

```jsx
import React from 'react';
import { useGLTF } from '@react-three/drei';

export function Model({ url, ...props }) {
  // Load the glTF asset from the public folder
  const { scene } = useGLTF(url);

  // Render the entire scene graph as a primitive object
  return <primitive object={scene} {...props} />;
}

// Preload the model to prevent freezing on first render
useGLTF.preload('/free_porsche_911_carrera_4s/scene.gltf');
```

---

## 4. Setting up the Canvas and Lighting

R3F requires a `<Canvas>` component to establish the WebGL rendering context. Good lighting and camera controls are essential for visualizing the model correctly.

### `src/App.js`

```jsx
import React, { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Environment, ContactShadows } from '@react-three/drei';
import { Model } from './Model';
import './styles.css';

export default function App() {
  return (
    <div style={{ height: '100vh', width: '100vw' }}>
      <Canvas camera={{ position: [0, 2, 5], fov: 50 }}>
        {/* Ambient light for base illumination */}
        <ambientLight intensity={0.5} />

        {/* Directional light for shadows and depth */}
        <directionalLight position={[10, 10, 5]} intensity={1} />

        {/* Environment map — crucial for PBR materials like metallic car paint */}
        <Environment preset="city" />

        {/* Suspense is required because useGLTF loads asynchronously */}
        <Suspense fallback={null}>
          <Model url="/free_porsche_911_carrera_4s/scene.gltf" />

          {/* Soft shadow cast on the floor beneath the model */}
          <ContactShadows
            resolution={1024}
            scale={10}
            blur={2}
            opacity={0.5}
            far={10}
          />
        </Suspense>

        {/* Orbit controls allow rotating, panning, and zooming with the mouse */}
        <OrbitControls makeDefault autoRotate autoRotateSpeed={0.5} />
      </Canvas>
    </div>
  );
}
```

---

## 5. CSS Requirements

Ensure root elements take up the full viewport so the Canvas renders correctly with no scrollbars or overflow.

### `src/styles.css`

```css
* {
  box-sizing: border-box;
}

body,
html,
#root {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
```

---

## 6. Key Concepts & Rules for AI Prompting

When AI agents are tasked with modifying this R3F implementation, they should adhere to the following conventions:

| Rule | Detail |
|---|---|
| **Always use `<Suspense>`** | `useGLTF` is async. Wrap all model components in `<Suspense>` or the render tree will break. |
| **Public-relative paths** | Asset URLs passed to `useGLTF` must be absolute relative to `public/` (e.g. `/model.gltf`, not `./model.gltf`). |
| **PBR Materials** | If the model has metallic/roughness materials, always include `<Environment>` from Drei to ensure physically correct reflections. |
| **Multiple Instances** | Use the `<Clone>` helper from Drei when rendering multiple copies of the same model to avoid duplicating geometry. |
| **Performance** | `useGLTF` caches loaded models automatically. Call `useGLTF.preload(url)` at module level to avoid hitching on first render. |
| **Shadows** | Enable `shadows` on `<Canvas>` and set `castShadow` / `receiveShadow` on meshes for real-time shadow maps. |
| **Animations** | If the glTF contains animations, use the `useAnimations` hook from Drei alongside `useGLTF` to drive `AnimationMixer`. |

---

## 7. Sandbox File Structure Reference

```
test/
  public/
    index.html
    free_porsche_911_carrera_4s/   ← glTF asset + textures live here
      scene.gltf
      textures/
  src/
    App.js        ← Canvas, lighting, controls
    Model.js      ← useGLTF model component
    index.js      ← React DOM entry point
    styles.css    ← Full-viewport CSS reset
  package.json
```
