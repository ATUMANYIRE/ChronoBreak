# CHRONOBREAK — Shot List

24.0 s · 24 fps · 576 frames (frame 1 = t 0.00 s, frame 576 = t 23.96 s) · 1920×1080

The film is **one continuous camera move with no cuts**. "Shots" are beats of a single take, so spatial continuity is guaranteed by construction. Every camera parameter is a monotone-cubic (PCHIP) track evaluated per frame in `scripts/animation_math.py::CameraRig`.

| Beat | Frames | Time | What happens | Camera | Clocks |
|---|---|---|---|---|---|
| **A: Awakening** | 1–96 | 0–4 s | Darkness. Layers of skeleton-watch gear trains tower overhead. A small amber pulse resting on a jewelled cradle at the clock centre flickers awake with a heartbeat flicker (from 0.9 s) and starts moving at 3.6 s. | 18→21 mm, low (3°→9°), slow orbit and push-in from 17 to 8 units, f/4.5→3.2 | world rate 1.0 |
| **B: Acceleration** | 97–216 | 4–9 s | The pulse climbs its curved path through rotating, meshing gear trains, trailing a comet streak whose length is proportional to its speed (0.8 → 3.3 units/s). | Chase from behind and to the side, 6.5 units, 21→24 mm | world rate 1.0 → 0.98 |
| **C: Distortion** | 217–360 | 9–15 s | The world clock decelerates (rate 1.0 → 0.025) while the pulse accelerates (3.3 → 13.7 units/s). Gears near the pulse slow further (rate × (1 − 0.92·D)) and the closest ones **fracture** into seeded shards. Each burst starts at a readable speed, then decelerates as world time keeps slowing. | Tighter chase, 5.2–5.4 units, 27 mm, f/2.2 | world rate → 0.025 |
| **D: Stillness** | 361–480 | 15–20 s | The pulse crosses a vast field of suspended shards (3,400 instances). From 16.2 to 18.6 s a **bullet-time beat** holds even the pulse (story rate 0.05) while the camera orbits about 190° around it, from behind to in front. Time snaps back and the pulse blasts past the lens toward the clock's edge. | Wide 20 mm orbit; camera decouples from the pulse at 18.15 s and turns to look forward | world 0.025 (near-total stillness), story 1 → 0.05 → 1 |
| **E: Reveal** | 481–576 | 20–24 s | The camera cranes up 420 units and rolls so that 12 o'clock is up. The glowing trail thickens into a gold **second hand**: the pulse's entire journey was the hand. A counterweight tail and boss fade in, dial lume rises, the hand **ticks** one second (60° → 66°) with a damped overshoot at 22.75 s, and the world clock resumes. The engraved title *CHRONOBREAK — WHEN SPEED BREAKS TIME* lights at 22.9–23.7 s. | Crane from 20 mm chase to a 32 mm top-down view on the clock axis | world rate → 1.0 |

## Why the reveal works geometrically

All four Bézier control points lie in the vertical plane through the clock axis at the second hand's angle (60°). Any point in that plane projects onto the same radial line for a camera on the axis, so a path that climbs, dives and curves in 3D during beats A–D becomes a perfectly straight hand in beat E. `tests/test_animation_math.py::test_path_projects_to_straight_second_hand` checks this to 1e-9.

## QA frames

1, 96, 216, 360, 480, 576 (shot boundaries) plus 48, 150, 300, 400, 430, 455, 500, 530 (inside beats and transitions).
