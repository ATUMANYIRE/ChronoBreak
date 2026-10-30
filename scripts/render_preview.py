"""Stage 1-3 renders: validation stills, the low-cost animatic, and benchmark frames.

    blender -b output/chronobreak.blend --python scripts/render_preview.py -- \
        --preset still --frames 1,96,216,360,480,576 [--out output/previews/stills]
    blender -b output/chronobreak.blend --python scripts/render_preview.py -- --preset animatic --all
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

from bl_util import abspath, apply_preset, load_cfg  # noqa: E402


def parse(argv):
    args = {"preset": "still", "frames": None, "all": False, "out": None, "step": 1}
    it = iter(argv)
    for a in it:
        if a == "--preset":
            args["preset"] = next(it)
        elif a == "--frames":
            args["frames"] = [int(x) for x in next(it).split(",")]
        elif a == "--all":
            args["all"] = True
        elif a == "--step":
            args["step"] = int(next(it))
        elif a == "--out":
            args["out"] = next(it)
    return args


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parse(argv)
    cfg, rcfg = load_cfg()
    scene = bpy.context.scene
    p = apply_preset(scene, args["preset"], rcfg)
    out_dir = abspath(args["out"] or os.path.join(rcfg["output"]["previews"], args["preset"]))
    os.makedirs(out_dir, exist_ok=True)
    frames = args["frames"] or list(range(scene.frame_start, scene.frame_end + 1, args["step"]))
    timings = []
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(out_dir, f"frame_{f:04d}.png")
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t0
        timings.append({"frame": f, "seconds": round(dt, 3)})
        print(f"[render] {args['preset']} frame {f} {dt:.2f}s", flush=True)
    log = {"preset": args["preset"], "settings": p, "frames": timings,
           "total_seconds": round(sum(x["seconds"] for x in timings), 2)}
    with open(os.path.join(out_dir, "render_log.json"), "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2)


if __name__ == "__main__":
    main()
