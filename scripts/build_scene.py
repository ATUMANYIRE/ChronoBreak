"""Build the complete CHRONOBREAK scene from config and save the .blend.

    blender -b --factory-startup --python scripts/build_scene.py [-- --preset still]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import procedural as pr  # noqa: E402
from animate_cameras import build_camera  # noqa: E402
from bl_util import abspath, apply_preset, load_cfg  # noqa: E402
from create_clockwork import build_clockwork  # noqa: E402
from create_materials import build_materials  # noqa: E402
from create_pulse import build_pulse  # noqa: E402
from generate_fragments import build_fragments  # noqa: E402
from setup_compositor import build_compositor  # noqa: E402
from setup_lighting import build_lighting  # noqa: E402


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def configure_scene(scene, cfg, rcfg):
    scene.render.fps = cfg["fps"]
    scene.frame_start = cfg["frame_start"]
    scene.frame_end = cfg["frame_end"]
    scene.render.engine = rcfg["engine"]
    vs = scene.view_settings
    vs.view_transform = "AgX"
    try:
        vs.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    vs.exposure = 0.0
    ee = scene.eevee
    ee.use_raytracing = True
    ee.ray_tracing_method = "SCREEN"
    ee.ray_tracing_options.resolution_scale = "2"
    ee.use_shadows = True
    ee.volumetric_start = 0.5
    ee.volumetric_end = 700.0
    ee.volumetric_tile_size = "8"
    ee.volumetric_samples = 48
    ee.motion_blur_steps = 1
    ee.use_fast_gi = True
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def main():
    t0 = time.time()
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preset = argv[argv.index("--preset") + 1] if "--preset" in argv else "final"
    cfg, rcfg = load_cfg()
    scene = reset_scene()
    configure_scene(scene, cfg, rcfg)

    tl, rig, gears, frags = pr.build_layout(cfg)
    print(f"[build] layout: {len(gears)} gears, {sum(g['fracture_t'] is not None for g in gears)} fracture, "
          f"{len(frags['origin'])} shards, path length {tl.path.length:.2f}")
    mats = build_materials()
    build_clockwork(cfg, tl, gears, mats)
    pulse = build_pulse(cfg, tl, mats)
    build_fragments(cfg, tl, frags, pulse["pulse"], mats)
    build_camera(cfg, tl)
    build_lighting(cfg, tl)
    build_compositor(scene)
    apply_preset(scene, preset, rcfg)
    scene.frame_set(cfg["frame_start"])

    out = abspath(rcfg["blend_file"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"[build] saved {out} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
