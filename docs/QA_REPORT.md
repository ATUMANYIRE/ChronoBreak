# CHRONOBREAK — QA Report

Visual QA is based on **looking at rendered frames**, not on a render merely finishing. Everything below was checked on the final 1920×1080 frames in `output/frames/` and on the encoded `output/CHRONOBREAK.mp4`, unless stated otherwise.

## 1. Technical verification (automated, measured)

| Check | Method | Result |
|---|---|---|
| Frame count on disk | `verify_output.py` | 576 / 576, none missing or undersized |
| Video duration | FFmpeg 7.1 stream probe | **24.0 s** |
| Decoded frame count | full FFmpeg decode | **576**, 0 errors |
| Resolution / fps / codec | FFmpeg probe | 1920×1080, 24 fps, H.264 High, yuv420p |
| Checksums | SHA-256 | `output/SHA256SUMS.txt`, `output/evidence/verification.json` |
| Unit and integration tests | `python run.py test` | **26 passed** (math, determinism, frame bounds, Blender scene integrity) |
| Scene integrity | `verify_output.py scene` | 354 objects, 122 gears (14 fractured), 4,975 shard instances matched to attributes, no errors |
| Cross-process determinism | 10 frames re-rendered in one fresh process vs. chunked originals | bit-identical (mean abs. diff ≤ 0.01/255) |
| Seams, pops, flicker | `scripts/scan_frames.py`, all 575 consecutive pairs | see §3 |

## 2. Frames inspected by eye

| Frame | t | Beat | Viewed at | Observation |
|---|---|---|---|---|
| 1 | 0.00 s | A | 960×540 + sheet | Low view under towering gear trains, cold rim highlights on gear teeth, amber cradle top in the foreground, pulse a small dim point. Reads as "dormant". |
| 48 | 1.96 s | A | sheet | Pulse brightening on its cradle; push-in. |
| 96 | 3.96 s | A→B | 960×540 | Pulse awake with halo, gear layers above. The cradle top is a large out-of-focus amber shape in the lower left (see §4). |
| 150 | 6.21 s | B | **1920×1080** | Sharp pulse, thin comet trail, readable meshing gear trains, a brass gear lit by the pulse. No artifacts. |
| 216 | 8.96 s | B→C | 960×540 | Pulse deep inside the mechanism, motion-blurred gear edges, first sparse shards in the distance. |
| 300 | 12.46 s | C | sheet | Larger halo, long streak, fracture debris beginning to fill the frame. |
| 360 | 14.96 s | C→D | 960×540 | Dense amber shard burst around the pulse, long streak. The strongest "speed breaks time" image. |
| 400 | 16.62 s | D | sheet | Bullet-time orbit: suspended shards, pulse held, trail a horizontal line. |
| 430 | 17.88 s | D | sheet | Orbit nearing front; shards close to the lens, motion-blurred. |
| 434–444 | 18.0–18.5 s | D | 480×270 strip | Time snaps back and the camera decouples: a 4–5 frame motion-blurred whip that brightens (frame 439) and then drops to near black (441). See §3. |
| 455 | 18.92 s | D | sheet | Camera looking forward through the frozen field; pulse leaving bottom right. |
| 480 | 19.96 s | D→E | 960×540 | Dark transitional frame: pulse and gold trail small at centre, faint shards and dial markers. Intentionally quiet before the crane. |
| 500 | 20.79 s | E | sheet + fixed render | Crane rising; dial ticks and the straight gold hand appear, gears below. |
| 510–521 | 21.2–21.7 s | E | 640×360 sheet, before and after fix | Before: grey haze veil and a luminance pop. After: dark field, smooth. See §3. |
| 530 | 22.04 s | E | sheet | Top-down skeleton clock on a black void, gold second hand at 60°, hour and minute hands, lume ticks. |
| 576 | 23.96 s | E | 960×540 + **1920×1080 crop** | Hand ticked to 66°. Title **CHRONOBREAK** clearly legible; the subtitle *WHEN SPEED BREAKS TIME* is small but legible at 1080p. |

Contact sheet of the 14 QA frames: `output/evidence/contact_sheet.png`.

## 3. Issues found and fixed

Earlier passes (stills and animatic):

| Issue | Fix |
|---|---|
| Centre arbor post blocked the camera in beats A and B | Arbor shortened and moved (z 31–44); camera and pulse sight-line clearance in the layout solver |
| Pulse halo too large and blown out | Halo scale 0.25 + 0.42·awake |
| Shard and haze white-outs | Shard glow and world density reduced |
| Large bokeh blobs from shards near the lens | `cull_near_camera` removes shards within 3.0 units of any camera position |
| White discs: the reveal softbox and rim lights mirrored in the glossy obsidian plate | Top light off during flight, `specular_factor` 0.15, obsidian roughness 0.45 and coat 0.35/0.28. Confirmed in frames 1, 420 and 440 |

In the final render:

| Issue | Evidence | Fix | Verified |
|---|---|---|---|
| **Grey haze veil and luminance pop in the reveal (frames ≈500–521).** Mean luma flickered 60 → 49 → 70 → 74, then fell to 39 in one frame. | `frame_diff_scan.json`; reproduced bit-for-bit in a fresh process, so not a seam | Reveal softbox `volume_factor = 0`; frames 471–576 re-rendered | Luma now rises smoothly 4 → 24 → 27 → 28 → 29 → 30 (frames 492–576). The fixed frames look clean. Frame 470 is bit-identical before and after |
| GPU compositor crash after 162 frames | crash log (`GPU_texture_ref` null in the render-pass read) | Chunked rendering, a fresh process per 40 frames | All 576 frames rendered |

Remaining large frame-to-frame changes, all inside the decouple whip at 17.7–18.4 s (frames 424–441, diffs 35–72 against a median of 6.2): this is the designed moment where bullet time ends and the camera turns away from the pulse. It is **kept as intentional**, but it is the harshest moment in the film (see §4). The diffs at every chunk boundary are in line with the neighbouring frames.

## 4. Known limitations (not fixed, documented)

- **Decouple whip (frames 438–441).** The motion-blurred whip brightens to a pale grey smear for about 2 frames and then cuts to near black. It reads as a "snap" at playback speed, but a smoother version would ease the camera's angular velocity or shorten the shutter there. I left it because it would mean re-rendering about 60 frames under deadline.
- **Foreground cradle in frames ≈60–110.** The defocused amber cradle top covers part of the lower-left frame during the awakening. It frames the pulse, but it is a large shape.
- **Subtitle size.** The subtitle is legible at 1080p but small. On a phone-sized player it reads as texture.
- **Grain.** At 24 samples there is faint shading noise on large dark surfaces (the cradle column in frame 1). A 48-sample benchmark showed no visible difference in the tested crops (`output/previews/bench_compare_crop.png`).
- **Shards are an analytic, art-directed model**, not a physical rigid-body simulation, and there is no collision between shards.
- The animatic was rendered without volumetrics and motion blur. Issues that depend on those (like the haze veil) only show at final settings, which is why the frame scan was added.

## 5. Sign-off

Technical checks pass and are measured. Visual QA: the inspected frames tell the intended story (awakening → acceleration → fracture → frozen field → second-hand reveal and title), and the one significant visual defect found in the final render was fixed and re-verified. The limitations in §4 are accepted for the Oct 31 2026 deadline.
