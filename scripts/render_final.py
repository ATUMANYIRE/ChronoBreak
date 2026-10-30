"""Stage 4: final frame render. Resumable: frames already on disk are skipped.

    blender -b output/chronobreak.blend --python scripts/render_final.py -- [--preset final] [--start 1 --end 576]
"""
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

from bl_util import abspath, apply_preset, load_cfg  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = {"--preset": "final", "--start": None, "--end": None}
    for k in opt:
        if k in argv:
            opt[k] = argv[argv.index(k) + 1]
    cfg, rcfg = load_cfg()
    scene = bpy.context.scene
    settings = apply_preset(scene, opt["--preset"], rcfg)
    out_dir = abspath(rcfg["output"]["frames"])
    os.makedirs(out_dir, exist_ok=True)
    start = int(opt["--start"] or scene.frame_start)
    end = int(opt["--end"] or scene.frame_end)
    log_path = abspath(os.path.join(rcfg["output"]["evidence"], "render_final_log.json"))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else {"frames": {}}
    log.update({"preset": opt["--preset"], "settings": settings, "blender": bpy.app.version_string,
                "machine": platform.processor() or platform.machine(), "platform": platform.platform()})
    for f in range(start, end + 1):
        path = os.path.join(out_dir, f"frame_{f:04d}.png")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        scene.frame_set(f)
        scene.render.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t0
        log["frames"][str(f)] = round(dt, 3)
        print(f"[final] frame {f}/{end} {dt:.2f}s", flush=True)
        if f % 8 == 0 or f == end:
            log["rendered_frames"] = len(log["frames"])
            log["total_render_seconds"] = round(sum(log["frames"].values()), 1)
            with open(log_path, "w", encoding="utf-8") as fh:
                json.dump(log, fh, indent=1)


if __name__ == "__main__":
    main()
