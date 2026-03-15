# Asset Review: glTF Integration Findings & Recommendations

> Review of the initial .glTF asset list against the current Chronos rendering
> pipeline, guided by `r3f-gltf-instructions.md`.

---

## 1. Current State Summary

### 1.1 Asset Files

| Asset | Present in Repo | Status |
|-------|:-:|--------|
| `abandoned_mansion_bedroom` | ❌ | Not yet downloaded / committed |
| `armor_set` | ❌ | Not yet downloaded / committed |
| `british_pub` | ❌ | Not yet downloaded / committed |
| `furniture_a_models_from_fps_creator_classic` | ❌ | Not yet downloaded / committed |
| `gameready_colt_python_revolver` | ❌ | Not yet downloaded / committed |
| `garden_table` | ❌ | Not yet downloaded / committed |
| `human_models_set_-_malefemale_rigged` | ❌ | Not yet downloaded / committed |
| `knight_-_includes_file_for_3d_printing` | ❌ | Not yet downloaded / committed |
| `medieval_tavern` | ❌ | Not yet downloaded / committed |
| `old_bar` | ❌ | Not yet downloaded / committed |
| `old_town` | ❌ | Not yet downloaded / committed |
| `restaurant_in_the_evening` | ❌ | Not yet downloaded / committed |
| `ruins_of_hore_abbey` | ❌ | Not yet downloaded / committed |
| `stylized_medieval_castle_room` | ❌ | Not yet downloaded / committed |
| `table_and_chairs_-_low_poly` | ❌ | Not yet downloaded / committed |

**Character GLBs** (cowboy, cowgirl, fighter, warrior) are referenced in code
and `.gitignore` but also absent from the repository.

**EXR environment maps** (kiara_1_dawn_4k, dikhololo_night_4k, canary_wharf_4k)
are referenced but absent.

### 1.2 Rendering Pipeline

| Capability | Implemented | Notes |
|-----------|:-:|-------|
| Primitive props (box/sphere/cylinder) | ✅ | `PlanProp` in Scene.tsx |
| GLTF character loading | ✅ | `GLTFCharacterModel` via `useGLTF` |
| GLTF prop/environment loading | ❌ | **No support** — all props render as primitives |
| Error boundary for models | ✅ | `ModelErrorBoundary` wraps character models |
| EXR environment maps | ✅ | `HDREnvironment` with preset fallback |
| PBR material properties | ✅ | `MATERIAL_PROPERTIES` lookup per material_type |
| Post-processing (bloom, vignette, DoF, noise) | ✅ | `EffectComposer` stack |
| Shadow maps | ✅ | 2048×2048, directional + contact shadows |

### 1.3 Data Model

The `Prop` model in `backend/models.py` supports only primitive shapes via
`ShapeType` (box, sphere, cylinder).  There is **no field** to reference a glTF
asset file.

The `SceneObjectBase` (legacy model) has an `asset` field for a `.glb` filename,
but this is part of the old `SceneState` path that renders objects as labelled
wireframe boxes — not true GLTF rendering.

---

## 2. Gap Analysis

### 2.1 Data Layer (backend/models.py)

| Gap | Impact | Recommendation |
|-----|--------|---------------|
| `Prop` has no `gltf_asset` field | Scene planner cannot reference GLTF assets for props | Add optional `gltf_asset: Optional[str]` to `Prop` |
| No asset catalog | No structured way to enumerate available assets | Create `asset_catalog.json` in `backend/assets/` |
| Scene planner system prompt doesn't mention GLTF assets | Gemini won't use available assets | Update system prompt with asset slug list |

### 2.2 Frontend Rendering (Scene.tsx)

| Gap | Impact | Recommendation |
|-----|--------|---------------|
| `PlanProp` renders only primitives | No visual realism for props | Add `GLTFPropModel` component; load `.glb` when `gltf_asset` is set |
| No asset slug → URL mapping | Frontend can't resolve asset slugs to file paths | Add `SCENE_ASSET_MAP` lookup table |
| No fallback pattern for prop GLTF | Missing `.glb` would crash | Wrap in `ModelErrorBoundary` + `Suspense`, fall back to primitive |
| GLTF props don't get scene's envMap | Reflections won't match | `<Environment>` already sets `scene.environment`; verify GLTF materials respond to it |
| No scale adjustment per asset | Assets at wrong scale | Apply `recommended_scale` from catalog × `GLB_TO_SCENE_SCALE` |

### 2.3 Asset Files

| Gap | Impact | Recommendation |
|-----|--------|---------------|
| No `.glb` files in repo | Nothing renders beyond primitives | Download, optimise (Draco), place in `frontend/public/assets/scenes/` |
| `.gitignore` blocks `.glb` files | Assets can't be committed | Add exclusion rules or use Git LFS for large binary assets |
| No EXR or character GLBs either | Environment maps and characters fall back to presets/capsules | Separate concern; tracked elsewhere |

### 2.4 Asset-Specific Concerns

| Asset | Category | Key Concern |
|-------|----------|-------------|
| `abandoned_mansion_bedroom` | environment | Verify room dimensions fit within 20 m bounds |
| `armor_set` | prop | Check poly count; may need LOD variant |
| `british_pub` | environment | Pre-baked lighting may conflict with dynamic lights |
| `furniture_a_models_from_fps_creator_classic` | prop_pack | Needs splitting into individual props |
| `gameready_colt_python_revolver` | prop | Small scale — verify precision at 0.01 conversion |
| `garden_table` | prop | Outdoor asset — check origin placement for y=0 |
| `human_models_set_-_malefemale_rigged` | character | Skeleton rig compatibility with animation_hint system |
| `knight_-_includes_file_for_3d_printing` | prop | Very high poly count expected; needs decimation |
| `medieval_tavern` | environment | Good candidate for first integration test |
| `old_bar` | environment | Similar to british_pub — verify differentiation |
| `old_town` | environment | Outdoor; may exceed room bounds; needs clipping |
| `restaurant_in_the_evening` | environment | Baked evening lighting — adjust envMapIntensity |
| `ruins_of_hore_abbey` | environment | Large outdoor ruin — partial loading required |
| `stylized_medieval_castle_room` | environment | Non-PBR art style may clash with other PBR props |
| `table_and_chairs_-_low_poly` | prop | Excellent perf profile; good first prop to integrate |

---

## 3. Recommendations (Priority Order)

### Phase 1 — Code Preparation (this PR)

1. ✅ **Create `r3f-gltf-instructions.md`** — establishes integration standards
2. ✅ **Create `backend/assets/asset_catalog.json`** — registers all 15 assets
3. ✅ **Add `gltf_asset` field to `Prop` model** — enables GLTF prop references
4. ✅ **Add `GLTFPropModel` and `SCENE_ASSET_MAP` to Scene.tsx** — renders GLTF
   props when available, falls back to primitive
5. ✅ **Update scene planner system prompt** — inform Gemini about available
   GLTF assets

### Phase 2 — Asset Acquisition

6. Download each asset from SketchFab (or original source)
7. Optimise with `gltf-transform` / Draco compression
8. Place optimised `.glb` files under `frontend/public/assets/scenes/<slug>/`
9. Update `.gitignore` to allow scene assets (or configure Git LFS)
10. Verify each asset loads and renders at correct scale

### Phase 3 — Polish & Realism

11. Tune `recommended_scale` and `position_y_offset` per asset
12. Adjust `envMapIntensity` per asset to match scene IBL
13. Add LOD variants for high-poly assets
14. Implement asset preloading (`useGLTF.preload`) for smoother transitions
15. Consider `gltfjsx` conversion for assets needing fine-grained interaction

---

*Review conducted: 2026-03-15*
