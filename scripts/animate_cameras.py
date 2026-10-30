"""One continuous camera move (no cuts), keyed per frame from animation_math.CameraRig."""
import bpy
import mathutils
import numpy as np

import animation_math as am
from bl_util import collection, keyframes, keyframes_vec


def build_camera(cfg, tl):
    col = collection("Camera")
    cam_data = bpy.data.cameras.new("ChronoCam")
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 3000.0
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_blades = 7
    cam = bpy.data.objects.new("ChronoCam", cam_data)
    col.objects.link(cam)
    bpy.context.scene.camera = cam

    rig = am.CameraRig(tl)
    ft = tl.frame_tables()
    n = len(ft["t"])
    loc = np.zeros((n, 3))
    rot = np.zeros((n, 3))
    lens, fstop, focus = np.zeros(n), np.zeros(n), np.zeros(n)
    prev = None
    for i, t in enumerate(ft["t"]):
        st = rig.state(float(t), ft["pos"][i], ft["s"][i])
        m = mathutils.Matrix(am.look_at_matrix(st["pos"], st["target"], st["up"]).tolist())
        e = m.to_euler("XYZ", prev) if prev is not None else m.to_euler("XYZ")
        prev = e
        loc[i], rot[i] = st["pos"], tuple(e)
        lens[i], fstop[i], focus[i] = st["lens"], st["fstop"], st["focus"]
    keyframes_vec(cam, "location", tl.frames, loc)
    keyframes_vec(cam, "rotation_euler", tl.frames, rot)
    keyframes(cam_data, "lens", tl.frames, lens)
    keyframes(cam_data, "dof.aperture_fstop", tl.frames, fstop)
    keyframes(cam_data, "dof.focus_distance", tl.frames, focus)
    return cam
