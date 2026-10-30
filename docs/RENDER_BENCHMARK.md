# CHRONOBREAK — Render Benchmark

All numbers below are measured wall-clock times from `render_log.json` / `render_final_log.json`, written by the render scripts. Nothing is estimated unless explicitly labelled as an estimate.

## Machine

| | |
|---|---|
| CPU | 13th Gen Intel Core i7-1355U (10 cores / 12 threads) |
| GPU | Intel UHD Graphics (integrated, driver 32.0.101.7088), no dedicated GPU |
| RAM | 15.6 GB |
| OS | Windows 11 Pro 10.0.26200 |
| Blender | 5.2.0 LTS, Eevee (`BLENDER_EEVEE`), background mode (`-b`) |

Cycles was not used. On this hardware Cycles would be CPU-only, and Eevee already gives the intended look: emissive pulse, metallic reflections through screen-space ray tracing, volumetric haze, motion blur and depth of field.

## Stage results

| Stage | Resolution | Samples | Motion blur | Volumetrics | Frames | Mean s/frame* | Min–max | Total |
|---|---|---|---|---|---|---|---|---|
| 1 · validation stills | 960×540 | 16 | off | on | 3 (latest pass) | 6.05 | 4.7–12.8 | 24.9 s |
| 2 · animatic | 640×360 | 4 | off | off | **576** | 1.84 | 1.39–9.49 | 1070 s (17.8 min) |
| 3 · benchmark A | 1920×1080 | 48 | on | on | 4 (96, 360, 420, 576) | 36.5 | 20.6–49.6 | 157 s |
| 3 · benchmark B | 1920×1080 | 24 | on | on | 4 (96, 360, 420, 576) | 19.8 | 11.6–33.7 | 93 s |

\*Mean excludes the first frame of each process, which includes shader compilation. The first-ever cold compile on this machine took 125.6 s for one frame; later processes reuse Blender's shader cache.

## Decision

A 100% crop comparison of frames 96 and 420 at 48 vs 24 samples (`output/previews/bench_compare_crop.png`) showed no visible difference: Eevee's temporal anti-aliasing and the post motion blur hide the extra samples. **The final uses 24 samples**, which roughly halves render time (benchmark mean 36.5 → 19.8 s/frame).

Final settings: 1920×1080, 24 TAA samples, motion blur (shutter 0.4, 1 step), screen-space ray tracing at ½ resolution, fast GI, volumetrics (tile 8 px, 48 samples, keyed density), depth of field, AgX *Medium High Contrast*, compositor bloom + dispersion + vignette, PNG RGB 8-bit.

## Stage 4 · final render (measured)

Source: `output/evidence/render_final_log.json` (per-frame wall-clock seconds, written after each saved frame).

| | |
|---|---|
| Frames on disk | **576 / 576** (`output/frames/frame_0001.png` … `frame_0576.png`, ≈1.2 GB PNG) |
| Frames with a logged time | 568 (frames 9–14 and 161–162 were saved by sessions that were killed or crashed before the log was written; the PNGs were verified present and full-size) |
| Sum of logged frame times | **8,163.9 s (2 h 16 min)** |
| Mean / median per frame | 14.37 s / 13.69 s |
| Fastest / slowest | 6.13 s / 36.36 s (frame 163, first frame of a fresh process, includes shader compile) |
| Device | Eevee on Intel UHD Graphics (integrated), i7-1355U, 15.6 GB RAM |

Per beat (logged frames only):

| Beat | Frames | Logged | Mean s/frame | Min–max |
|---|---|---|---|---|
| A · awakening | 1–96 | 90 | 16.89 | 11.53–21.93 |
| B · acceleration | 97–216 | 118 | 19.70 | 16.73–36.35 |
| C · distortion | 217–360 | 144 | 13.89 | 9.87–25.70 |
| D · stillness | 361–480 | 120 | 12.74 | 6.73–20.09 |
| E · reveal | 481–576 | 96 | 8.23 | 6.13–14.15 |

The dense gear interior (A–B, with close metallic surfaces filling the frame under screen-space ray tracing) is the expensive part, not the 3,400-shard field: shards are instances of 8 meshes and render cheaply.

### What happened during the final render

1. **Out-of-memory kill.** The first attempt ran as a background process from the AI coding session and was terminated by that tool's low-memory watchdog after 14 frames. The render was then run from a normal terminal.
2. **GPU compositor crash.** After 162 frames (≈45 min in a single Blender session) Blender exited with `EXCEPTION_ACCESS_VIOLATION`. The crash log shows a null texture in `GPU_texture_ref` ← `render::Context::get_pass` ← the GPU compositor's Render Layer node: a render-pass texture was not allocated. On an integrated GPU, video memory is shared system RAM, so long sessions are the likely trigger. **Fix:** `python run.py final` now runs a fresh Blender process per 40-frame chunk, with up to 3 retries; `render_final.py` skips frames already on disk. The chunked run then rendered the remaining 414 frames to completion. Every frame from 163 on has a logged time, and the end of the console output shows each chunk exiting cleanly. I did not review the full console output for retried chunks.
3. **Chunk seams checked.** Because each chunk is a separate process, consecutive-frame differences were measured across the whole sequence (`output/evidence/frame_diff_scan.json`). Differences at every chunk boundary are in line with neighbouring frames. Ten frames (514–523) re-rendered in a single fresh process were **bit-identical** (mean abs. difference ≤ 0.01/255) to the chunked originals, so rendering is deterministic across processes.
4. **Reveal re-render (frames 471–576).** The same scan showed a luminance flicker and a sudden drop at frames 505–521 (mean luma 49 → 70 → 39 within a few frames). It reproduced in a fresh render, so it was a scene issue, not a seam: the reveal top softbox (energy up to 1.1 MW) was scattering into the fading world volume and veiling the dial in grey. The animatic had volumetrics off, so it never showed in preview. The fix sets the softbox's `volume_factor` to 0; it still lights the dial. Frames 471–576 were re-rendered (106 frames, mean 8.2 s). Frame 470, rendered before and after the fix, is bit-identical, so earlier frames are unaffected. The superseded frames are not part of the deliverable.

## Stage 5 · encode and verification (measured)

`python run.py encode` → `output/CHRONOBREAK.mp4`: libx264, preset *slow*, CRF 16, High profile, yuv420p, `+faststart`.

`python run.py verify` (`output/evidence/verification.json`), measured with the FFmpeg 7.1 binary bundled by imageio-ffmpeg (no separate `ffprobe` was installed; duration and stream properties come from FFmpeg's stream probe, and the frame count comes from a full decode):

| Check | Result |
|---|---|
| Duration | **24.0 s** |
| Decoded frames | **576**, 0 decode errors |
| Resolution / fps | 1920×1080 / 24 |
| Codec / pixel format | H.264 / yuv420p |
| File size | 29,379,027 bytes (28.0 MiB), ≈ 9.8 Mbit/s |

SHA-256 values are in `output/SHA256SUMS.txt`.
