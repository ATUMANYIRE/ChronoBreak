"""One-command entry points for CHRONOBREAK (Windows / macOS / Linux).

    python run.py build      # regenerate output/chronobreak.blend from config + scripts
    python run.py test       # pytest (math, determinism, bounds, Blender scene integrity)
    python run.py stills     # stage 1: validation stills -> output/previews/still
    python run.py animatic   # stage 2: full 640x360 animatic -> output/previews/animatic.mp4
    python run.py benchmark  # stage 3: 1080p benchmark frames -> output/previews/benchmark
    python run.py final      # stage 4: 1080p frames -> output/frames (resumable)
    python run.py encode     # stage 5: H.264 MP4 -> output/CHRONOBREAK.mp4
    python run.py verify     # frames, video (ffmpeg probe + decode), SHA-256
    python run.py evidence   # contact sheet + frame-difference scan + Blender UI screenshot
    python run.py all        # build, test, final, encode, verify, evidence
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import animation_math as am  # noqa: E402

RCFG = am.load_config("render.json")
BLENDER = os.environ.get("BLENDER", RCFG["blender_exe"])
BLEND = os.path.join(ROOT, RCFG["blend_file"])
QA_FRAMES = "1,48,96,150,216,300,360,400,430,455,480,500,530,576"


def sh(*cmd):
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def blender(script, *args, blend=True):
    base = [BLENDER, "-b"] + ([BLEND] if blend else ["--factory-startup"])
    sh(*base, "--python", os.path.join(ROOT, "scripts", script), "--", *args)


def render_final_chunked(chunk=40, retries=3):
    """Fresh Blender process per chunk: long single sessions on the integrated GPU eventually
    crash in the GPU compositor (null render-pass texture). render_final.py skips finished frames,
    so a crashed chunk is simply retried."""
    cfg = am.load_config("scene.json")
    frames_dir = os.path.join(ROOT, RCFG["output"]["frames"])
    for start in range(cfg["frame_start"], cfg["frame_end"] + 1, chunk):
        end = min(start + chunk - 1, cfg["frame_end"])
        done = all(os.path.exists(os.path.join(frames_dir, f"frame_{f:04d}.png")) for f in range(start, end + 1))
        if done:
            continue
        for attempt in range(1, retries + 1):
            try:
                blender("render_final.py", "--start", str(start), "--end", str(end))
                break
            except subprocess.CalledProcessError as exc:
                print(f"[final] chunk {start}-{end} attempt {attempt} failed (exit {exc.returncode})", flush=True)
                if attempt == retries:
                    raise


def main(cmd):
    py = sys.executable
    if cmd == "build":
        blender("build_scene.py", blend=False)
    elif cmd == "test":
        sh(py, "-m", "pytest", "tests", "-q")
    elif cmd == "stills":
        blender("render_preview.py", "--preset", "still", "--frames", QA_FRAMES)
        sh(py, "scripts/capture_evidence.py", "contact", "--dir", "output/previews/still", "--frames", QA_FRAMES,
           "--out", "output/previews/still_sheet.png", "--width", "480")
    elif cmd == "animatic":
        blender("render_preview.py", "--preset", "animatic", "--all")
        sh(py, "scripts/encode_video.py", "--frames", "output/previews/animatic", "--out", "output/previews/animatic.mp4")
    elif cmd == "benchmark":
        blender("render_preview.py", "--preset", "benchmark", "--frames", "96,360,430,576")
    elif cmd == "final":
        render_final_chunked()
    elif cmd == "encode":
        sh(py, "scripts/encode_video.py")
    elif cmd == "verify":
        sh(py, "scripts/verify_output.py", "video")
    elif cmd == "evidence":
        sh(py, "scripts/capture_evidence.py", "contact", "--frames", QA_FRAMES, "--cols", "4", "--width", "480")
        sh(py, "scripts/scan_frames.py")
        sh(py, "scripts/capture_evidence.py", "screenshot")
    elif cmd == "all":
        for c in ("build", "test", "final", "encode", "verify", "evidence"):
            main(c)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "help")
