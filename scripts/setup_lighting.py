"""Lighting hierarchy: the pulse is the key light; cold rims carve silhouettes; a top
softbox and world haze rise only for the reveal."""
import bpy
import mathutils
import numpy as np

import animation_math as am
from bl_util import collection, keyframes, socket_path


def _area(name, col, loc, target, size, color, energy):
    data = bpy.data.lights.new(name, "AREA")
    data.shape = "DISK"
    data.size = size
    data.color = color
    data.energy = energy
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    obj.location = loc
    d = mathutils.Vector(target) - mathutils.Vector(loc)
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return obj


def build_lighting(cfg, tl):
    col = collection("Lighting")
    tm = cfg["timing"]
    frames = tl.frames
    t = tl.frame_to_time(frames)

    world = bpy.data.worlds.get("ChronoWorld") or bpy.data.worlds.new("ChronoWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.0012, 0.0013, 0.0017, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.name = "Volume"
    vol.inputs["Color"].default_value = (0.9, 0.85, 0.8, 1.0)
    vol.inputs["Anisotropy"].default_value = 0.55
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    reveal = am.smootherstep(tm["reveal_start"], tm["reveal_end"], t)
    keyframes(nt, socket_path(vol, "Density"), frames, 0.0028 * (1 - reveal) + 0.00005 * reveal)

    rim_a = _area("RimCold_A", col, (-170, 80, 30), (0, 0, 8), 90, (0.55, 0.66, 1.0), 3.0e5)
    rim_b = _area("RimCold_B", col, (140, -150, 18), (20, 20, 6), 70, (0.6, 0.7, 1.0), 2.0e5)
    warm = _area("WarmUnder", col, (60, 40, -40), (40, 25, 10), 60, (1.0, 0.6, 0.3), 5.0e4)
    top = _area("RevealTop", col, (-20, 40, 340), (0, 0, 0), 320, (1.0, 0.95, 0.9), 1.0e6)
    top.data.specular_factor = 0.15  # never mirror the softbox in the obsidian plate
    top.data.volume_factor = 0.0  # lights the dial only; scattering it in the haze veiled the pull-back
    keyframes(top.data, "energy", frames, 1.1e6 * reveal)
    for o in (rim_a, rim_b):
        keyframes(o.data, "energy", frames, o.data.energy * (0.55 + 0.45 * am.smoothstep(0.0, 4.0, t)) * (1 - 0.6 * reveal))
    return {"world": world, "top": top}
