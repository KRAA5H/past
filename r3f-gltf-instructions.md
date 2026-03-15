# React Three Fiber — glTF Asset Integration Guide

> Best practices for loading, configuring, and rendering `.gltf` / `.glb` assets
> in the **Chronos** 3-D historical-scene application.

---

## 1. Asset Pipeline Overview

| Stage | Tool / Library | Notes |
|-------|---------------|-------|
| **Authoring** | Blender / SketchFab export | Export as `.glb` (binary glTF) for smaller file size |
| **Optimisation** | `gltf-transform`, `gltfpack` | Draco / meshopt compression, texture resize |
| **Conversion to JSX** | `@react-three/gltfjsx` (`npx gltfjsx model.glb -t`) | Optional — generates typed React component |
| **Runtime loading** | `useGLTF` from `@react-three/drei` | Suspense-aware, caches by URL |
| **Rendering** | `<primitive object={scene} />` or JSX components | Clone scene when reusing the same model |

---

## 2. File Organisation

```
frontend/public/
├── models/                    # Character GLB files
│   ├── cowboy.glb
│   ├── cowgirl.glb
│   └── ...
└── assets/
    └── scenes/                # Environment / prop GLTF assets
        ├── abandoned_mansion_bedroom/
        │   └── scene.glb
        ├── british_pub/
        │   └── scene.glb
        └── ...
```

- **Character models** live under `/models/` and are mapped via `ARCHETYPE_MODEL_MAP`.
- **Scene / prop assets** live under `/assets/scenes/<asset_slug>/` and are mapped
  via the `SCENE_ASSET_MAP` lookup table in `Scene.tsx`.
- Backend serves EXR environment maps and audio files from `backend/assets/`
  via the FastAPI `/assets` static-file mount.

---

## 3. Loading with `useGLTF`

```tsx
import { useGLTF } from '@react-three/drei'

function MyModel({ url }: { url: string }) {
  const { scene } = useGLTF(url)

  // Clone when the same model may appear more than once in the scene
  const cloned = useMemo(() => {
    const c = scene.clone(true)
    c.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        child.castShadow = true
        child.receiveShadow = true
      }
    })
    return c
  }, [scene])

  return <primitive object={cloned} />
}
```

### Key points

| Concern | Recommendation |
|---------|---------------|
| **Suspense** | Always wrap `<MyModel>` in `<Suspense fallback={…}>` so the scene stays interactive while loading. |
| **Error boundary** | Wrap in `ModelErrorBoundary` to fall back to a primitive shape when the asset is missing or fails to load. |
| **Cloning** | Call `scene.clone(true)` before passing to `<primitive>` to avoid shared-state issues when the same model appears multiple times. |
| **Shadows** | Traverse the cloned scene and enable `castShadow` / `receiveShadow` on every mesh. |
| **Disposal** | `useGLTF` handles cleanup when the component unmounts. |

---

## 4. Placement, Scaling & Rotation

### 4.1 Scale

Most SketchFab assets are authored at **centimetre** scale (1 unit = 1 cm).
Chronos scenes use **metre** scale, so a conversion factor is needed:

```ts
const GLB_TO_SCENE_SCALE = 0.01   // cm → m
```

Each asset in the **asset catalog** (`backend/assets/asset_catalog.json`) records
a `recommended_scale` value.  The frontend multiplies this with
`GLB_TO_SCENE_SCALE` to obtain the final uniform scale.

### 4.2 Position

Assets should be placed using the scene's metre-based coordinate system:

- **x, z** : horizontal plane, range `[-10, 10]`
- **y** : vertical, `0` = ground plane, range `[0, 5]`

Ground-level assets should have `y = 0` (the asset's own origin should sit on
the floor).  If the model's origin is not at its base, apply a `position-y`
offset listed in the catalog.

### 4.3 Rotation

Apply a Y-axis rotation (in degrees) to orient the asset toward the scene's
focal point.  The `rotation_y` field on `Prop` is converted to radians in the
renderer.

---

## 5. Materials & Physically Based Rendering

### 5.1 Embedded PBR materials

glTF assets from SketchFab usually ship with full PBR material data
(baseColorTexture, metallicRoughness, normalMap, occlusionMap, emissiveMap).
**Preserve these** — do not replace them with flat colours.

When a glTF asset is loaded, the existing `meshPhysicalMaterial` overrides used
for primitive props should **not** be applied.  The renderer should:

1. Keep the original textures and material settings.
2. Optionally adjust `envMapIntensity` to match the scene's IBL.

### 5.2 Tone-mapping & Colour Space

- Set `renderer.toneMapping = THREE.ACESFilmicToneMapping` for cinematic look.
- Ensure texture colour spaces are correct (`sRGB` for base colour, `Linear`
  for roughness / metallic).
- `@react-three/fiber` handles colour-space conversion automatically when
  `flat={false}` (default).

### 5.3 Environment Map Integration

Use the scene's HDR/EXR environment map as the `envMap` for all meshes to get
accurate reflections and ambient lighting:

```tsx
<Environment files={exrPath} background />
```

The `<Environment>` component from `@react-three/drei` automatically sets
`scene.environment`, which Three.js applies to all `MeshStandardMaterial` /
`MeshPhysicalMaterial` instances.

---

## 6. Performance Considerations

| Technique | When to Use |
|-----------|------------|
| **Draco compression** | Always — reduces download size by 80–90 %. `useGLTF.preload(url)` + drei handles the Draco decoder automatically. |
| **Level of Detail (LOD)** | Assets with > 100 k triangles. Provide a low-poly variant and switch based on camera distance. |
| **Instancing** | Multiple identical props (e.g. chairs around a table). Use `<Instances>` from drei. |
| **Texture atlasing** | Many small textures. Combine into fewer, larger textures to reduce draw calls. |
| **Frustum culling** | Three.js enables this by default per mesh. Ensure bounding spheres are correct. |
| **Preloading** | Call `useGLTF.preload(url)` at module level to start downloading before the component mounts. |

---

## 7. Asset Catalog Integration

Each listed asset is registered in `backend/assets/asset_catalog.json` with:

```json
{
  "slug": "british_pub",
  "name": "British Pub",
  "category": "environment",
  "file_path": "/assets/scenes/british_pub/scene.glb",
  "recommended_scale": 1.0,
  "position_y_offset": 0.0,
  "tags": ["indoor", "medieval", "victorian", "social"],
  "suitable_architecture_styles": ["victorian", "medieval_european"],
  "notes": "Full interior with bar counter, tables, and fireplace."
}
```

The **scene planner** can reference asset slugs in the `gltf_asset` field on
`Prop`.  When the frontend sees a `gltf_asset` value, it loads the
corresponding `.glb` file **instead of** rendering a primitive shape.

---

## 8. Prop Model: Primitive vs. glTF

The `Prop` Pydantic model supports two rendering modes:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `shape` | `ShapeType` | required | Primitive fallback shape (`box`, `sphere`, `cylinder`) |
| `gltf_asset` | `str \| None` | `None` | Asset catalog slug; when set, the frontend loads the glTF model instead of the primitive |

The **primitive shape** always remains as the fallback, so scenes render even
when the `.glb` file is unavailable.

---

## 9. Shadow & Lighting Checklist

- [x] `castShadow` and `receiveShadow` on every mesh in cloned GLTF scene
- [x] Directional light with 2048 × 2048 shadow map (`shadow-mapSize`)
- [x] `ContactShadows` for soft ground-level shadows
- [x] `shadow-bias` tuned to avoid acne (`-0.0001`)
- [x] `ambientLight` for fill; intensity 0.15 for indoor scenes
- [x] EXR environment map for realistic IBL reflections

---

## 10. Post-Processing Stack

The renderer applies (via `@react-three/postprocessing`):

| Effect | Purpose |
|--------|---------|
| **Bloom** | Glow on emissive surfaces (candles, monitors) |
| **Vignette** | Darkened edges for cinematic framing |
| **DepthOfField** | Subtle bokeh to draw focus |
| **Noise** | Film-grain at low opacity for period feel |

Keep `Bloom.luminanceThreshold` ≥ 0.6 to avoid over-brightening non-emissive
GLTF meshes.

---

## 11. Error Handling Pattern

```
<ModelErrorBoundary fallback={<PrimitiveFallback />}>
  <Suspense fallback={<PrimitiveFallback />}>
    <GLTFPropModel url={assetUrl} scale={scale} />
  </Suspense>
</ModelErrorBoundary>
```

This guarantees the scene is always renderable — if the `.glb` fails to load,
the viewer sees the primitive shape with the correct material colour and
dimensions.

---

## 12. Migration Path

1. **Phase 1 (current):** Primitive-only props + character GLBs.
   Assets listed in the catalog but not yet downloaded.
2. **Phase 2:** Download / optimise assets, place `.glb` files under
   `frontend/public/assets/scenes/`.  Update `gltf_asset` on props.
3. **Phase 3:** Generate scene-specific GLTF components with `gltfjsx` for
   fine-grained control (animation, interaction hotspots).

---

*Last updated: 2026-03-15*
