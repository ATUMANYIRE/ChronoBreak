# CHRONOBREAK — Technical Workflow

## Pipeline

```
config/scene.json ─┐
config/render.json ┤
                   ▼
scripts/animation_math.py   pure NumPy: Bézier + arc length, clocks, D(x,t), fragments, camera rig
scripts/procedural.py       pure NumPy: gear meshes, gear-train layout, fracture events, shard attributes
                   │   (both importable without Blender → tested by pytest)
                   ▼
scripts/build_scene.py (Blender) ── create_materials → create_clockwork → create_pulse
                                  → generate_fragments → animate_cameras → setup_lighting
                                  → setup_compositor → output/chronobreak.blend
                   ▼
render_preview.py (stills / animatic / benchmark) → render_final.py (resumable frames)
                   ▼
encode_video.py (FFmpeg H.264) → verify_output.py (scene + video + SHA-256) → capture_evidence.py
```

`python run.py <build|test|stills|animatic|benchmark|final|encode|verify|evidence|all>` wraps every stage.

## Mathematical systems (`scripts/animation_math.py`)

**Path.** A cubic Bézier `B(u) = (1-u)³P0 + 3(1-u)²u P1 + 3(1-u)u² P2 + u³P3` whose control points are given as (radius, height) in the second hand's vertical plane. `ArcLengthBezier` builds an 8,193-sample chord-length table and inverts it with linear interpolation, so the pulse travels by **arc length s**, not by `u`. This matters because equal steps in `u` differ in length by more than 20% on this curve (`test_raw_parameter_is_not_distance`). Path length is 114.96 units, matching 64-point Gauss–Legendre quadrature to 1e-5.

**Three clocks**, each defined by a rate and integrated from t = 0 with a fixed 240 Hz trapezoid grid (`integrate_rate`):

| Clock | Rate | Purpose |
|---|---|---|
| real time *t* | 1 | the viewer |
| story time τ(t) | 1 − 0.95·(smoothstep(16.2, 16.8) − smoothstep(18.0, 18.6)) | bullet-time beat (stops even the pulse) |
| world time T_w(t) | 1 − 0.975·smoothstep(8.5, 15) + 0.975·smoothstep(20.2, 22.4) | the environment slows as the pulse accelerates, then resumes |

**Acceleration.** `v(x) = v0 + a·x^p` with v0 = 1, a = 0.081, p = 2.2, x = τ − 3.6 s. Its integral `F(x) = v0·x + a·x^(p+1)/(p+1)` is normalised by `F(X_end)` so that progress reaches exactly 1 at t = 20 s, then multiplied by the arc length. The resulting intrinsic speed rises from 0.8 to 23.4 units/s.

**Distortion field.** `D(x,t) = exp(−‖x − P(t)‖² / 2σ²)`, σ = 5. It drives:
- gear rotation rate `ω·g(t)·(1 − 0.92·D(c,t))`, integrated per gear train (`gear_train_angles`);
- fracture events: a gear fractures at the pulse's closest approach if the pulse passes within 7.5 units of its disc between 9.3 and 19.7 s;
- illumination: `D` is keyed into each gear's object colour and read by its material as amber emission; the shards evaluate `D²` live in Geometry Nodes;
- the pulse light's energy, which scales with speed.

**Fragments.** Each shard follows
`x_i(t) = x_i0 + d_i·s(t) + A_i·(sin(ω_i·T_w + φ_i) − sin(ω_i·trigger_i + φ_i))`,
`s(t) = 1 − exp(−k·max(T_w − trigger_i, 0)·gain_i)` (bounded envelope, k = 2.4).
`gain_i = 0.55 / g(t_fracture)` rescales each burst to its world rate at the moment of fracture: bursts start readable, then freeze as world time keeps slowing. A shock-front delay of `dist/45` staggers shards by distance from the impact. This is an art-directed analytic model, **not** a rigid-body simulation.

**Frame independence.** Every keyed value is a pure function of the frame number. Cumulative tables are just a fast evaluation of the same integrals; `test_cumulative_equals_independent_integral` and `test_gear_angle_cumulative_matches_single` check that they equal the independent per-frame integrals.

**Camera.** `CameraRig.state(t)` places the camera in a spherical offset (distance, azimuth, elevation) around an anchor on the path, measured in the clock's (radial, side, up) frame so the rig never spins with the path tangent. Tracks are monotone cubic (Fritsch–Carlson PCHIP). In beat E the position, look-at target, up vector (Z → Y), focal length and f-stop blend with smootherstep into the exact top-down view on the clock axis. Euler angles are made continuous with `Matrix.to_euler('XYZ', previous)`.

**Tick.** `θ(t) = −6°·(1 − e^(−18x)·cos 26x)`: a snap with damped overshoot.

## Procedural geometry (`scripts/procedural.py`)

- **Gears**: 10 archetypes (12–120 teeth, module 1) built from a 7-point trapezoidal tooth profile (root, pitch, tip), rim and hub annular prisms, and box spokes. Each gear object is a **linked duplicate** sharing its archetype mesh (instancing), scaled by its module. Arbors (shared cylinder mesh) and dial ticks and markers (two shared meshes, 60 objects) are instanced the same way.
- **Layout**: seeded (`numpy.random.default_rng(seed)`) rejection sampling, 60% biased toward the path. Trains of 1–3 **properly meshing gears**: centre distance = (N1 + N2)·m/2, ratio −N1/N2, and phase `θ2 = α + π − π/N2 − (N1/N2)(θ1 − α)` so a tooth meets a gap. Rejection tests cover overlap between gears, the clock radius, the pulse path (1.7 clearance), every camera position (1.4), every camera→pulse sight line (0.35), and **top-view occlusion of the second hand**, so nothing can hide the hand in the reveal.
- **Shards**: 8 archetypes from `bmesh.ops.convex_hull` of seeded points in flattened ellipsoids (slivers of broken plate). Gear shards are sampled area-uniformly on each fractured gear's rim; the shot-D field is sampled in a tube around the path segment the pulse crosses from 15 to 19 s, avoiding the camera path and intact gears.

## Geometry Nodes (`scripts/generate_fragments.py`)

`ShardField` is a vertex-only mesh: one vertex per shard, carrying 12 seeded attributes (`p_dir`, `p_trig`, `p_gain`, `p_amp`, `p_omega`, `p_phase`, `p_scale`, `p_rot0`, `p_axis`, `p_spin`, `p_tint`, `p_variant`). The `ChronoShards` node group evaluates the fragment equation above, the distortion glow from the pulse's evaluated location (Object Info), and a fracture flash `exp(−3τ)`. It stores `glow` and instances the picked archetype with an Euler base rotation composed with an axis-angle spin. The only animated input is **World Time**, keyed per frame. The shard material reads `p_tint` and `glow` through *Instancer* attribute nodes.

## Look development

- Materials are fully procedural: concentric "circular graining" from a Rings wave texture in object space, driving roughness and bump (titanium, brass, blued steel); obsidian main plate with clear coat and ring bump; emission for the pulse, streak, hand and lume. No image textures.
- Lighting hierarchy: the moving amber point light in the pulse is the key light; two cold disk rims carve silhouettes; a warm under-fill; a large top softbox and dial lume rise only for the reveal. The softbox has `volume_factor = 0`: it lights the dial but does not scatter in the haze, which otherwise veiled the pull-back in grey. A world volume (principled volume, anisotropy 0.55) provides atmosphere and is keyed almost to zero for the reveal so the void stays black.
- Compositor (Blender 5.x node-group compositor): Glare (Bloom, high quality), Lens Distortion dispersion 0.012, and an elliptical vignette (blurred mask remapped to 0.55–1, multiplied).
- Colour management: AgX, *Medium High Contrast* look.
- Eevee: screen-space ray tracing for metal reflections, fast GI, virtual shadow maps, motion blur (shutter 0.4), depth of field keyed per frame (focus on the pulse).

## Rendering robustness

- `run.py final` renders in 40-frame chunks, one fresh Blender process each, with up to 3 retries per chunk. It skips frames already on disk, so an interrupted run resumes where it stopped. This was introduced after a GPU-compositor access violation 162 frames into a single long session on the integrated GPU (see `RENDER_BENCHMARK.md`).
- Rendering is deterministic across processes: re-rendered frames are bit-identical to the chunked originals.
- A consecutive-frame difference scan over all 576 frames (luma of 240×135 thumbnails) catches seams, pops and flicker that individual stills hide.

## Blender 5.2 API notes encountered

- Geometry Nodes modifier inputs are no longer ID properties: use `mod.properties.inputs.<Socket_N>.value`; the keyable path is `modifiers["Shards"].properties.inputs.Socket_N.value`.
- The compositor is `scene.compositing_node_group` with a `NodeGroupOutput`; there is no Composite node, and Glare and Lens Distortion settings are node inputs.
- F-curves are reached through slotted actions: `bpy_extras.anim_utils.action_get_channelbag_for_slot`.
