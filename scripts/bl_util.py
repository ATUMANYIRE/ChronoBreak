"""Small bpy helpers shared by the CHRONOBREAK build and render scripts."""
import os
import sys

import bpy
import numpy as np
from bpy_extras import anim_utils

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import animation_math as am  # noqa: E402

INTERP = {"CONSTANT": 0, "LINEAR": 1, "BEZIER": 2}


def collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if col.name not in parent.children:
        parent.children.link(col)
    return col


def link(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def mesh_object(name, verts, faces, col, material=None, smooth_angle=None, mesh=None):
    if mesh is None:
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
        mesh.validate()
        if material is not None:
            mesh.materials.append(material)
        if smooth_angle is not None:
            mesh.shade_smooth()
            mesh.set_sharp_from_angle(angle=smooth_angle)
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    return obj


def keyframes(owner, data_path, frames, values, index=-1, interp="LINEAR"):
    """Write a whole F-curve in one go (fast foreach_set) on any animatable ID."""
    frames = np.asarray(frames, dtype=float)
    values = np.asarray(values, dtype=float)
    owner.keyframe_insert(data_path=data_path, index=index, frame=float(frames[0]))
    ad = owner.animation_data
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    fc = bag.fcurves.find(data_path, index=max(index, 0))
    kp = fc.keyframe_points
    kp.clear()
    kp.add(len(frames))
    co = np.empty(2 * len(frames))
    co[0::2], co[1::2] = frames, values
    kp.foreach_set("co", co)
    kp.foreach_set("interpolation", [INTERP[interp]] * len(frames))
    fc.update()
    return fc


def keyframes_vec(owner, data_path, frames, values, interp="LINEAR"):
    values = np.asarray(values, dtype=float)
    for i in range(values.shape[1]):
        keyframes(owner, data_path, frames, values[:, i], index=i, interp=interp)


def load_cfg():
    return am.load_config("scene.json"), am.load_config("render.json")


def abspath(rel):
    return os.path.join(am.ROOT, rel)


def apply_preset(scene, preset_name, render_cfg=None):
    """Resolution, samples, motion blur and volumetric quality from config/render.json."""
    render_cfg = render_cfg or am.load_config("render.json")
    p = render_cfg["presets"][preset_name]
    r = scene.render
    r.engine = render_cfg["engine"]
    r.resolution_x, r.resolution_y = p["resolution"]
    r.resolution_percentage = 100
    scene.eevee.taa_render_samples = p["samples"]
    r.use_motion_blur = p["motion_blur"]
    r.motion_blur_shutter = render_cfg["motion_blur_shutter"]
    world = scene.world
    if world and world.node_tree and "Volume" in world.node_tree.nodes:
        world.node_tree.nodes["Volume"].mute = not p["volumetrics"]
    scale = p["resolution"][0] / 1920.0
    ng = scene.compositing_node_group
    if ng and "VignetteBlur" in ng.nodes:
        ng.nodes["VignetteBlur"].inputs["Size"].default_value = (260 * scale, 260 * scale)
    return p


def socket_path(node, name):
    """Animatable data path of a node input looked up by name (index-robust)."""
    for i, s in enumerate(node.inputs):
        if s.name == name:
            return f'nodes["{node.name}"].inputs[{i}].default_value'
    raise KeyError(name)
