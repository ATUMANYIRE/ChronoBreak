"""Stage 5: encode rendered PNG frames to H.264 MP4 with FFmpeg.

    python scripts/encode_video.py [--frames output/frames] [--out output/CHRONOBREAK.mp4]
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import animation_math as am  # noqa: E402


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("FFmpeg not found: install ffmpeg or `pip install imageio-ffmpeg`") from exc


def encode(frame_dir, out, fps, start, crf, preset, pix_fmt):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", str(fps), "-start_number", str(start),
           "-i", os.path.join(frame_dir, "frame_%04d.png"),
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", pix_fmt,
           "-profile:v", "high", "-movflags", "+faststart", "-r", str(fps), out]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    return out


if __name__ == "__main__":
    cfg, rcfg = am.load_config("scene.json"), am.load_config("render.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default=os.path.join(am.ROOT, rcfg["output"]["frames"]))
    ap.add_argument("--out", default=os.path.join(am.ROOT, rcfg["output"]["video"]))
    a = ap.parse_args()
    e = rcfg["encode"]
    print(encode(a.frames, a.out, cfg["fps"], cfg["frame_start"], e["crf"], e["preset"], e["pix_fmt"]))
