"""Consecutive-frame difference scan: finds seams, pops and flicker that single stills hide.

    python scripts/scan_frames.py [--dir output/frames] [--out output/evidence/frame_diff_scan.json]

Each frame is reduced to a 240x135 luma thumbnail; the scan reports mean luma per frame and the
mean absolute difference to the previous frame, flagging the largest jumps and every
40-frame render-chunk boundary (see run.py render_final_chunked).
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

import animation_math as am


def scan(frames_dir, first, last):
    prev, diffs, lum = None, [], []
    for f in range(first, last + 1):
        im = Image.open(os.path.join(frames_dir, f"frame_{f:04d}.png")).convert("L").resize((240, 135))
        a = np.asarray(im, dtype=np.float32)
        lum.append(float(a.mean()))
        if prev is not None:
            diffs.append((f, float(np.abs(a - prev).mean())))
        prev = a
    return diffs, lum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(am.ROOT, "output", "frames"))
    ap.add_argument("--out", default=os.path.join(am.ROOT, "output", "evidence", "frame_diff_scan.json"))
    ap.add_argument("--chunk", type=int, default=40)
    args = ap.parse_args()
    cfg = am.load_config("scene.json")
    first, last = cfg["frame_start"], cfg["frame_end"]
    diffs, lum = scan(args.dir, first, last)
    d = dict(diffs)
    v = np.array(list(d.values()))
    print(f"median diff {np.median(v):.2f}  max {v.max():.2f}")
    for f, x in sorted(diffs, key=lambda t: -t[1])[:10]:
        print(f"  frame {f}: diff {x:.2f}  luma {lum[f - first]:.1f}")
    bounds = {b: round(d[b], 2) for b in range(first + args.chunk, last + 1, args.chunk)}
    print("chunk boundaries:", bounds)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"first_frame": first, "diffs": diffs, "luma": lum, "chunk_boundaries": bounds}, fh)
    print(args.out)


if __name__ == "__main__":
    main()
