"""Verification.

Scene integrity (inside Blender, prints one JSON line prefixed 'SCENE_REPORT'):
    blender -b output/chronobreak.blend --python scripts/verify_output.py -- scene

Frames + video + checksums (system Python):
    python scripts/verify_output.py video [--video output/CHRONOBREAK.mp4]
"""
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import animation_math as am  # noqa: E402

REQUIRED_OBJECTS = ["ChronoCam", "Pulse", "PulseLight", "SecondHand", "Streak", "HandTrail", "HandTail",
                    "ShardField", "MainPlate", "Bezel", "ChapterRing", "HourHand", "MinuteHand", "Title"]


def scene_report():
    import bpy

    cfg = am.load_config("scene.json")
    sc = bpy.context.scene
    errors = []
    missing = [n for n in REQUIRED_OBJECTS if n not in bpy.data.objects]
    if missing:
        errors.append(f"missing objects: {missing}")
    if sc.camera is None or sc.camera.name != "ChronoCam":
        errors.append("scene camera is not ChronoCam")
    if (sc.frame_start, sc.frame_end, sc.render.fps) != (cfg["frame_start"], cfg["frame_end"], cfg["fps"]):
        errors.append("frame range / fps mismatch")
    no_mat = [o.name for o in sc.objects if o.type in {"MESH", "CURVE", "FONT"} and not o.hide_render
              and o.name not in ("ShardField",) and not any(s.material for s in o.material_slots)]
    if no_mat:
        errors.append(f"objects without material: {no_mat[:10]}")
    gears = [o for o in sc.objects if o.name.startswith("Gear_")]
    bad = []
    for f in (1, 96, 216, 360, 400, 480, 576):
        sc.frame_set(f)
        for o in sc.objects:
            if not all(math.isfinite(v) for row in o.matrix_world for v in row):
                bad.append((o.name, f))
    if bad:
        errors.append(f"non-finite transforms: {bad[:10]}")
    sc.frame_set(400)
    deps = bpy.context.evaluated_depsgraph_get()
    n_inst = sum(1 for inst in deps.object_instances if inst.is_instance and inst.parent
                 and inst.parent.name == "ShardField")
    shard_count = int(bpy.data.objects["ShardField"].get("shard_count", 0))
    if n_inst != shard_count:
        errors.append(f"shard instances {n_inst} != {shard_count}")
    fractured = sum(1 for g in gears if g.get("fracture_time", -1) >= 0)
    report = {
        "blender": bpy.app.version_string, "engine": sc.render.engine,
        "frames": [sc.frame_start, sc.frame_end], "fps": sc.render.fps,
        "resolution": [sc.render.resolution_x, sc.render.resolution_y],
        "samples": sc.eevee.taa_render_samples, "motion_blur": sc.render.use_motion_blur,
        "objects": len(sc.objects), "gears": len(gears), "fractured_gears": fractured,
        "shard_instances_at_400": n_inst, "materials": len(bpy.data.materials),
        "errors": errors, "ok": not errors,
    }
    print("SCENE_REPORT " + json.dumps(report))
    return report


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", head[16:24])


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video(path):
    """ffprobe-equivalent using the ffmpeg binary: stream header + full decode frame count."""
    from encode_video import ffmpeg_exe

    exe = ffmpeg_exe()
    info = subprocess.run([exe, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    dec = subprocess.run([exe, "-hide_banner", "-v", "error", "-stats", "-i", path, "-map", "0:v:0", "-f", "null", "-"],
                         capture_output=True, text=True)
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    vid = re.search(r"Video: (\w+).*?, (\w+)\(?.*?, (\d{3,5})x(\d{3,5})", info)
    fps = re.search(r"([\d.]+) fps", info)
    frames = re.findall(r"frame=\s*(\d+)", dec.stderr)
    return {
        "duration_s": int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else None,
        "codec": vid.group(1) if vid else None,
        "pix_fmt": vid.group(2) if vid else None,
        "resolution": [int(vid.group(3)), int(vid.group(4))] if vid else None,
        "fps": float(fps.group(1)) if fps else None,
        "decoded_frames": int(frames[-1]) if frames else None,
        "decode_errors": dec.stderr.count("Error") + (dec.returncode != 0),
    }


def video_report(video):
    cfg, rcfg = am.load_config("scene.json"), am.load_config("render.json")
    frame_dir = os.path.join(am.ROOT, rcfg["output"]["frames"])
    n = cfg["frame_end"] - cfg["frame_start"] + 1
    want = rcfg["presets"]["final"]["resolution"]
    errors = []
    frames = [os.path.join(frame_dir, f"frame_{f:04d}.png") for f in range(cfg["frame_start"], cfg["frame_end"] + 1)]
    missing = [p for p in frames if not os.path.exists(p)]
    if missing:
        errors.append(f"{len(missing)} missing frames, first {os.path.basename(missing[0])}")
    wrong = [os.path.basename(p) for p in frames if os.path.exists(p) and list(png_size(p)) != want]
    if wrong:
        errors.append(f"wrong frame resolution: {wrong[:5]}")
    v = probe_video(video) if os.path.exists(video) else None
    if v is None:
        errors.append("video missing")
    else:
        if v["decoded_frames"] != n:
            errors.append(f"decoded {v['decoded_frames']} frames, expected {n}")
        if v["resolution"] != want:
            errors.append(f"video resolution {v['resolution']}")
        if v["codec"] != "h264":
            errors.append(f"codec {v['codec']}")
        if not (5.0 <= (v["duration_s"] or 0) <= 30.0):
            errors.append(f"duration {v['duration_s']}")
        if abs((v["fps"] or 0) - cfg["fps"]) > 1e-6:
            errors.append(f"fps {v['fps']}")
        if v["decode_errors"]:
            errors.append("decode errors")
    blend = os.path.join(am.ROOT, rcfg["blend_file"])
    checksums = {}
    evidence_dir = os.path.join(am.ROOT, rcfg["output"]["evidence"])
    evidence = [os.path.join(evidence_dir, f) for f in ("blender_wip_screenshot.png", "contact_sheet.png")]
    for p in (video, blend, *evidence):
        if os.path.exists(p):
            checksums[os.path.relpath(p, am.ROOT).replace("\\", "/")] = {"sha256": sha256(p), "bytes": os.path.getsize(p)}
    report = {"video": v, "frames_present": n - len(missing), "frames_expected": n,
              "checksums": checksums, "errors": errors, "ok": not errors}
    out = os.path.join(am.ROOT, rcfg["output"]["evidence"], "verification.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(am.ROOT, "output", "SHA256SUMS.txt"), "w", encoding="utf-8") as fh:
        for k, c in checksums.items():
            fh.write(f"{c['sha256']}  {k}\n")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    mode = args[0] if args else "video"
    if mode == "scene":
        r = scene_report()
    else:
        rcfg = am.load_config("render.json")
        video = args[args.index("--video") + 1] if "--video" in args else os.path.join(am.ROOT, rcfg["output"]["video"])
        r = video_report(video)
    sys.exit(0 if r["ok"] else 1)
