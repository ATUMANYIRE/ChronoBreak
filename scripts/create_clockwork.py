"""The clock universe: gear trains, arbors, bridges, dial, hands, hub and title."""
import math

import bpy
import numpy as np

import animation_math as am
import procedural as pr
from bl_util import collection, keyframes, mesh_object, socket_path

GEAR_MATS = ["titanium", "brass", "blued"]


def lume_metal(name, color, base):
    """Polished metal whose amber lume (emission) is keyed on node 'BSDF'."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "BSDF"
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.2
    bsdf.inputs["Emission Color"].default_value = color
    bsdf.inputs["Emission Strength"].default_value = 0.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def prism(poly, z0, z1):
    n = len(poly)
    verts = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return verts, faces


def sector(r0, r1, a0, a1, z0, z1, seg=48):
    a = np.linspace(a0, a1, seg)
    outer = [(r1 * math.cos(t), r1 * math.sin(t)) for t in a]
    inner = [(r0 * math.cos(t), r0 * math.sin(t)) for t in a[::-1]]
    return prism(outer + inner, z0, z1)


def cylinder(r, z0, z1, seg=32):
    return prism([(r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, seg, endpoint=False)], z0, z1)


def hand_blade(length, tail, width):
    w = width
    return [(-0.6 * w, -tail), (0.6 * w, -tail), (w, 0.0), (0.7 * w, 0.85 * length),
            (0.0, length), (-0.7 * w, 0.85 * length), (-w, 0.0)]


def build_clockwork(cfg, tl, gears, mats):
    root = collection("Clockwork")
    col_gears = collection("Gears", root)
    col_static = collection("Dial", root)
    cc = cfg["clock"]
    smooth = math.radians(32)

    # archetype meshes shared by every gear of that tooth count (linked duplicates)
    arch_mesh = {}
    for i, arch in enumerate(pr.GEAR_ARCHETYPES):
        v, f = pr.gear_mesh(arch["teeth"], arch["spokes"])
        me = bpy.data.meshes.new(f"GearArch_{arch['teeth']}T")
        me.from_pydata(v, [], f)
        me.validate()
        me.materials.append(mats["titanium"])
        me.shade_smooth()
        me.set_sharp_from_angle(angle=smooth)
        arch_mesh[i] = me
    av, af = cylinder(1.0, -0.5, 0.5, 24)
    arbor_mesh = bpy.data.meshes.new("Arbor")
    arbor_mesh.from_pydata(av, [], af)
    arbor_mesh.materials.append(mats["titanium_static"])
    arbor_mesh.shade_smooth()
    arbor_mesh.set_sharp_from_angle(angle=smooth)

    frames = tl.frames
    t = tl.frame_to_time(frames)
    ft = tl.frame_tables()
    trains = sorted({g["train"] for g in gears})
    drivers = {g["train"]: g for g in gears if g["ratio"] == 1.0}
    train_angle = am.gear_train_angles(
        tl, [drivers[k]["driver_center"] for k in trains], [drivers[k]["omega"] for k in trains],
        cfg["distortion"]["gear_slow_k"], t)
    train_row = {k: i for i, k in enumerate(trains)}

    objs = []
    for gi, g in enumerate(gears):
        m = g["module"]
        obj = mesh_object(f"Gear_{gi:03d}", None, None, col_gears, mesh=arch_mesh[g["arch"]])
        obj.location = tuple(g["center"])
        obj.scale = (m, m, m * 0.85)
        slot = obj.material_slots[0]
        slot.link = "OBJECT"
        slot.material = mats[GEAR_MATS[int(g["tint"])]]
        theta = g["phase"] + g["ratio"] * train_angle[train_row[g["train"]]]
        keyframes(obj, "rotation_euler", frames, theta, index=2)
        glow = am.distortion(g["center"], ft["pos"], tl.sigma)
        keyframes(obj, "color", frames, glow, index=0)
        obj["fracture_time"] = -1.0 if g["fracture_t"] is None else g["fracture_t"]
        arbor = mesh_object(f"Arbor_{gi:03d}", None, None, col_gears, mesh=arbor_mesh)
        d = pr.gear_dims(g["teeth"])
        arbor.location = tuple(g["center"])
        arbor.scale = (d["bore"] * m * 0.95, d["bore"] * m * 0.95, 2 * g["half_h"] + 1.4 * m)
        if g["fracture_t"] is not None:
            f_frac = int(round(g["fracture_t"] * tl.fps)) + tl.frame_start
            for o in (obj, arbor):
                for prop in ("hide_render", "hide_viewport"):
                    keyframes(o, prop, [frames[0], f_frac], [0.0, 1.0], interp="CONSTANT")
        objs.append(obj)

    # dial architecture
    v, f = pr.annulus_mesh(2.0, cc["bezel_radius"] + 2.0, -7.0, -6.0, 256)
    mesh_object("MainPlate", v, f, col_static, mats["obsidian"])
    v, f = pr.annulus_mesh(cc["chapter_outer"] + 0.6, cc["bezel_radius"], -6.0, 3.0, 256)
    bezel = mesh_object("Bezel", v, f, col_static, mats["titanium_static"], smooth)
    v, f = pr.annulus_mesh(cc["chapter_inner"], cc["chapter_outer"], -1.2, 0.0, 256)
    ring = mesh_object("ChapterRing", v, f, col_static, mats["blued"], smooth)
    ring.color = (0, 0, 0, 1)

    lume = lume_metal("DialLume", (1.0, 0.62, 0.22, 1.0), (0.7, 0.7, 0.72, 1.0))
    mats["lume"] = lume
    tick_v, tick_f = prism([(-0.35, 0), (0.35, 0), (0.35, 9.0), (-0.35, 9.0)], 0.0, 0.5)
    tick_mesh = bpy.data.meshes.new("MinuteTick")
    tick_mesh.from_pydata(tick_v, [], tick_f)
    tick_mesh.materials.append(lume)
    mark_v, mark_f = prism([(-1.3, 0), (1.3, 0), (1.0, 15.0), (-1.0, 15.0)], 0.0, 1.1)
    mark_mesh = bpy.data.meshes.new("HourMarker")
    mark_mesh.from_pydata(mark_v, [], mark_f)
    mark_mesh.materials.append(lume)
    for k in range(60):
        hour = k % 5 == 0
        o = mesh_object(f"{'Marker' if hour else 'Tick'}_{k:02d}", None, None, col_static,
                        mesh=mark_mesh if hour else tick_mesh)
        a = math.radians(6 * k)
        r0 = 106.5 if hour else 113.0
        o.location = (r0 * math.sin(a), r0 * math.cos(a), 0.0)
        o.rotation_euler = (0, 0, -a)

    # bridges: arched plates floating over the train, clear of the second hand and title
    hand = cc["hand_angle_deg"]
    for i, (centre_deg, r0, r1, span, z) in enumerate([(150, 44, 54, 50, 31.5), (255, 58, 66, 44, 31.5),
                                                       (338, 30, 38, 34, 31.5), (110, 74, 82, 30, 31.5)]):
        a0 = math.radians(90 - centre_deg - span / 2)
        a1 = math.radians(90 - centre_deg + span / 2)
        assert abs(((centre_deg - hand + 180) % 360) - 180) > span / 2 + 8
        v, f = sector(r0, r1, a0, a1, z, z + 1.2)
        b = mesh_object(f"Bridge_{i}", v, f, col_static, mats["titanium_static"], smooth)
        for a in (a0 + 0.06, a1 - 0.06):
            sv, sf = cylinder(1.4, z + 1.2, z + 1.8, 24)
            sc = mesh_object(f"BridgeJewel_{i}", sv, sf, col_static, lume)
            sc.location = ((r0 + r1) / 2 * math.cos(a), (r0 + r1) / 2 * math.sin(a), 0)
        b.color = (0, 0, 0, 1)

    # hub, hour and minute hands
    v, f = cylinder(2.2, 31.0, 44.0, 48)
    mesh_object("CentreArbor", v, f, col_static, mats["titanium_static"], smooth)
    v, f = cylinder(3.4, -6.0, 1.6, 64)
    mesh_object("PulseCradle", v, f, col_static, mats["titanium_static"], smooth)
    v, f = cylinder(2.6, 1.6, 2.1, 48)
    mesh_object("CradleJewel", v, f, col_static, lume)
    v, f = cylinder(4.6, 41.4, 43.0, 64)
    cap = mesh_object("HubCap", v, f, col_static, mats["brass"], smooth)
    cap.color = (0, 0, 0, 1)
    v, f = cylinder(1.5, 43.0, 43.6, 32)
    mesh_object("HubJewel", v, f, col_static, lume)
    for name, ang, length, tail, width, z in (("HourHand", cc["hour_angle_deg"], 62.0, 14.0, 4.6, 36.0),
                                              ("MinuteHand", cc["minute_angle_deg"], 94.0, 18.0, 3.4, 39.0)):
        v, f = prism(hand_blade(length, tail, width), z, z + 1.0)
        h = mesh_object(name, v, f, col_static, mats["titanium_static"], smooth)
        h.rotation_euler = (0, 0, -math.radians(ang))
        v, f = prism(hand_blade(length * 0.62, -length * 0.22, width * 0.42), z + 1.0, z + 1.15)
        inl = mesh_object(name + "Lume", v, f, col_static, lume)
        inl.rotation_euler = (0, 0, -math.radians(ang))

    # title, engraved above the 12 o'clock train like a watch dial signature
    for name, body, size, y, extrude in (("Title", "CHRONOBREAK", 7.0, 50.0, 0.25),
                                         ("Subtitle", "WHEN SPEED BREAKS TIME", 2.4, 42.5, 0.1)):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = body
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.size = size
        cu.extrude = extrude
        cu.space_character = 1.25 if name == "Title" else 1.6
        txt = bpy.data.objects.new(name, cu)
        col_static.objects.link(txt)
        txt.location = (0.0, y, 33.6)
        cu.materials.append(mats["title"])

    # dial lume and title glow during the reveal
    tm = cfg["timing"]
    lume_curve = 0.15 + 5.0 * am.smoothstep(tm["reveal_start"] + 1.0, tm["reveal_end"], t)
    keyframes(lume.node_tree, socket_path(lume.node_tree.nodes["BSDF"], "Emission Strength"), frames, lume_curve)
    title_curve = 9.0 * am.smootherstep(tm["title_in"][0], tm["title_in"][1], t)
    title_em = mats["title"].node_tree.nodes["Emission"]
    keyframes(mats["title"].node_tree, socket_path(title_em, "Strength"), frames, title_curve)
    return objs
