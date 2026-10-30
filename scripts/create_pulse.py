"""The amber pulse, its speed streak, and the trail that becomes the second hand."""
import math

import bpy
import numpy as np

import animation_math as am
from bl_util import collection, keyframes, keyframes_vec, socket_path


def _bezier_curve(name, ctrl, col, mat, depth, resolution=128):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = resolution
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(1)
    a, b = sp.bezier_points
    a.co, a.handle_right, a.handle_left = tuple(ctrl[0]), tuple(ctrl[1]), tuple(2 * ctrl[0] - ctrl[1])
    b.co, b.handle_left, b.handle_right = tuple(ctrl[3]), tuple(ctrl[2]), tuple(2 * ctrl[3] - ctrl[2])
    for p in (a, b):
        p.handle_left_type = p.handle_right_type = "FREE"
    cu.bevel_depth = depth
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    cu.bevel_factor_mapping_start = "SPLINE"
    cu.bevel_factor_mapping_end = "SPLINE"
    cu.materials.append(mat)
    obj = bpy.data.objects.new(name, cu)
    col.objects.link(obj)
    return obj


def _taper(name, col, pts):
    cu = bpy.data.curves.new(name, "CURVE")
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, (x, y) in zip(sp.points, pts):
        p.co = (x, y, 0.0, 1.0)
    obj = bpy.data.objects.new(name, cu)
    col.objects.link(obj)
    obj.hide_render = True
    obj.hide_viewport = True
    return obj


def build_pulse(cfg, tl, mats):
    col = collection("Pulse")
    helpers = collection("PulseHelpers")
    frames = tl.frames
    t = tl.frame_to_time(frames)
    ft = tl.frame_tables()
    tm = cfg["timing"]
    awake = tl.awaken(t)

    hand = bpy.data.objects.new("SecondHand", None)
    hand.empty_display_type = "ARROWS"
    col.objects.link(hand)
    keyframes(hand, "rotation_euler", frames, am.tick_angle(t, tm["tick_time"], cfg["clock"]["tick_deg"]), index=2)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.26)
    core = bpy.context.active_object
    core.name = "Pulse"
    for c in core.users_collection:
        c.objects.unlink(core)
    col.objects.link(core)
    core.data.materials.append(mats["pulse_core"])
    core.data.shade_smooth()
    core.parent = hand
    keyframes_vec(core, "location", frames, ft["pos"])
    em = mats["pulse_core"].node_tree.nodes["Emission"]
    keyframes(mats["pulse_core"].node_tree, socket_path(em, "Strength"), frames, 2.0 + 70.0 * awake)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0)
    halo = bpy.context.active_object
    halo.name = "PulseHalo"
    for c in halo.users_collection:
        c.objects.unlink(halo)
    col.objects.link(halo)
    halo.data.materials.append(mats["pulse_halo"])
    halo.data.shade_smooth()
    halo.parent = core
    speed = ft["speed"]
    halo_scale = (0.25 + 0.42 * awake) * (1.0 + 0.012 * speed)
    keyframes_vec(halo, "scale", frames, np.repeat(halo_scale[:, None], 3, axis=1))

    light_data = bpy.data.lights.new("PulseLight", "POINT")
    light_data.color = (1.0, 0.52, 0.16)
    light_data.shadow_soft_size = 0.35
    light = bpy.data.objects.new("PulseLight", light_data)
    col.objects.link(light)
    light.parent = core
    keyframes(light_data, "energy", frames, 10.0 + 1800.0 * awake * (1.0 + speed / 30.0))

    ctrl = [np.array(p) for p in tl.ctrl]
    L = tl.path.length

    # speed streak: tail length proportional to the pulse's intrinsic speed, comet taper
    streak = _bezier_curve("Streak", ctrl, col, mats["streak"], 0.085)
    streak.data.taper_object = _taper("StreakTaper", helpers, [(0, 0.0), (0.7, 0.35), (0.95, 0.85), (1.0, 1.0)])
    streak.data.use_map_taper = True
    streak.parent = hand
    length = np.clip(0.55 * speed, 0.0, 26.0)
    i_arr = int(np.argmax(t >= tm["pulse_arrive"]))
    after = t >= tm["pulse_arrive"]
    length[after] = length[i_arr - 1] * np.exp(-6.0 * (t[after] - tm["pulse_arrive"]))
    f = ft["progress"]
    keyframes(streak.data, "bevel_factor_end", frames, np.clip(f + 0.002, 0, 1))
    keyframes(streak.data, "bevel_factor_start", frames, np.clip(f - length / L, 0, 1))

    # persistent trail = the second hand. Thin during flight, thickens at the reveal.
    trail = _bezier_curve("HandTrail", ctrl, col, mats["hand"], 1.0)
    trail.data.taper_object = _taper("HandTaper", helpers, [(0, 1.0), (0.5, 0.8), (1.0, 0.45)])
    trail.data.use_map_taper = False
    trail.parent = hand
    keyframes(trail.data, "bevel_factor_end", frames, np.clip(f, 0.0005, 1))
    w_rev = am.smootherstep(tm["reveal_start"] + 0.6, tm["reveal_end"] - 0.3, t)
    keyframes(trail.data, "bevel_depth", frames, 0.05 + 1.25 * w_rev)
    hem = mats["hand"].node_tree.nodes["Emission"]
    keyframes(mats["hand"].node_tree, socket_path(hem, "Strength"), frames, 2.0 * awake + 16.0 * w_rev)

    # counterweight tail and boss appear with the reveal
    tail_dir = -tl.clock.radial
    cu = bpy.data.curves.new("HandTail", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(1)
    sp.points[0].co = (0.0, 0.0, 3.0, 1.0)
    p1 = tail_dir * 24.0 + np.array([0.0, 0.0, 3.0])
    sp.points[1].co = (p1[0], p1[1], p1[2], 1.0)
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    cu.materials.append(mats["hand"])
    tail = bpy.data.objects.new("HandTail", cu)
    col.objects.link(tail)
    tail.parent = hand
    keyframes(cu, "bevel_depth", frames, 0.001 + 1.5 * am.smootherstep(tm["reveal_start"] + 1.6, tm["reveal_end"], t))
    bpy.ops.mesh.primitive_torus_add(major_radius=3.2, minor_radius=0.7, major_segments=64, minor_segments=12)
    boss = bpy.context.active_object
    boss.name = "HandCounterweight"
    for c in boss.users_collection:
        c.objects.unlink(boss)
    col.objects.link(boss)
    boss.data.materials.append(mats["hand"])
    boss.location = tuple(tail_dir * 20.0 + np.array([0.0, 0.0, 3.0]))
    boss.parent = hand
    s = am.smootherstep(tm["reveal_start"] + 1.6, tm["reveal_end"], t)
    keyframes_vec(boss, "scale", frames, np.repeat(np.maximum(s, 1e-3)[:, None], 3, axis=1))
    return {"pulse": core, "hand": hand, "streak": streak, "trail": trail}
