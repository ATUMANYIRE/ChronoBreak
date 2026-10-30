"""Evidence: contact sheets from real rendered frames, and a genuine Blender UI screenshot.

    python scripts/capture_evidence.py contact --dir output/frames --frames 1,96,216,360,480,576 \
        --out output/evidence/contact_sheet.png [--cols 3 --width 640]
    python scripts/capture_evidence.py screenshot      # opens Blender's UI and grabs the window
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import animation_math as am  # noqa: E402
from encode_video import ffmpeg_exe  # noqa: E402


def contact_sheet(frame_dir, frames, out, cols=3, width=640, prefix="frame_", fps=24):
    paths = [os.path.join(frame_dir, f"{prefix}{f:04d}.png") for f in frames]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(missing)
    height = int(width * 9 / 16)
    rows = (len(paths) + cols - 1) // cols
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    for p in paths:
        cmd += ["-i", p]
    chains, labels = [], []
    for i, f in enumerate(frames):
        label = f"F{f}  {(f - 1) / fps:05.2f}s"
        chains.append(f"[{i}:v]scale={width}:{height},drawtext=text='{label}':x=10:y=10:fontsize=20:"
                      f"fontcolor=white:box=1:boxcolor=black@0.55:fontfile='C\:/Windows/Fonts/consola.ttf'[v{i}]")
        labels.append(f"[v{i}]")
    n = len(paths)
    pad = rows * cols - n
    for j in range(pad):
        chains.append(f"color=c=black:s={width}x{height}:d=1[p{j}]")
        labels.append(f"[p{j}]")
    layout = "|".join(f"{(k % cols) * width}_{(k // cols) * height}" for k in range(rows * cols))
    filt = ";".join(chains) + ";" + "".join(labels) + f"xstack=inputs={rows * cols}:layout={layout}[out]"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    subprocess.run(cmd + ["-filter_complex", filt, "-map", "[out]", "-frames:v", "1", out], check=True)
    return out


def blender_screenshot(out):
    """Launch Blender with its UI, frame the scene, save a full-window screenshot, quit."""
    rcfg = am.load_config("render.json")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ui_screenshot.py")
    blend = os.path.join(am.ROOT, rcfg["blend_file"])
    env = dict(os.environ, CHRONO_SCREENSHOT=os.path.abspath(out))
    subprocess.run([rcfg["blender_exe"], blend, "--python", script], check=True, env=env, timeout=600)
    if not os.path.exists(out):
        raise RuntimeError("Blender did not write the screenshot")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["contact", "screenshot"])
    ap.add_argument("--dir", default=os.path.join(am.ROOT, "output", "frames"))
    ap.add_argument("--frames", default="1,96,216,360,480,576")
    ap.add_argument("--out", default=None)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--width", type=int, default=640)
    a = ap.parse_args()
    if a.mode == "contact":
        out = a.out or os.path.join(am.ROOT, "output", "evidence", "contact_sheet.png")
        print(contact_sheet(a.dir, [int(x) for x in a.frames.split(",")], out, a.cols, a.width))
    else:
        print(blender_screenshot(a.out or os.path.join(am.ROOT, "output", "evidence", "blender_wip_screenshot.png")))
