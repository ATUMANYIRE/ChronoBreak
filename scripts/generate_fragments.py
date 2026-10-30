"""Shard archetypes + a Geometry Nodes system that evaluates the fragment model per frame.

Each shard is a vertex of 'ShardField' carrying seeded attributes. The node tree computes
    tau  = max(T_w - trigger, 0) * gain
    s    = 1 - exp(-k tau)                         (bounded envelope)
    x    = x0 + d s + A (sin(w T_w + phi) - sin(w trigger + phi))
    glow = max(D(x, P(t)), 0.8 exp(-3 tau))        (distortion field + fracture flash)
and instances one of eight convex-hull shard meshes, so every frame is a pure function of
the keyed world-time input; nothing is simulated or cached.
"""
import bmesh
import bpy
import numpy as np

import procedural as pr
from bl_util import collection, keyframes

ATTRS = {  # name -> (fragment key, data type, components)
    "p_dir": ("dir", "FLOAT_VECTOR"), "p_trig": ("trigger", "FLOAT"), "p_gain": ("gain", "FLOAT"),
    "p_amp": ("amp", "FLOAT_VECTOR"), "p_omega": ("omega", "FLOAT"), "p_phase": ("phase", "FLOAT"),
    "p_scale": ("scale", "FLOAT"), "p_rot0": ("rot0", "FLOAT_VECTOR"), "p_axis": ("axis", "FLOAT_VECTOR"),
    "p_spin": ("spin", "FLOAT"), "p_tint": ("tint", "FLOAT"), "p_variant": ("variant", "INT"),
}


def shard_archetypes(seed, mat):
    col = collection("ShardArchetypes")
    rng = np.random.default_rng(seed + 7)
    for i in range(8):
        pts = pr.shard_points(rng)
        bm = bmesh.new()
        for p in pts:
            bm.verts.new(p)
        bmesh.ops.convex_hull(bm, input=bm.verts)
        me = bpy.data.meshes.new(f"ShardArch_{i}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        obj = bpy.data.objects.new(f"ShardArch_{i}", me)
        col.objects.link(obj)
    lc = bpy.context.view_layer.layer_collection.children[col.name]
    lc.exclude = True
    return col


def _attr_node(nt, name, dtype, loc):
    n = nt.nodes.new("GeometryNodeInputNamedAttribute")
    n.data_type = dtype
    n.inputs["Name"].default_value = name
    n.location = loc
    return n.outputs["Attribute"]


def _math(nt, op, a, b=None, loc=(0, 0)):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.location = loc
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _vmath(nt, op, a, b=None, scale=None, loc=(0, 0)):
    n = nt.nodes.new("ShaderNodeVectorMath")
    n.operation = op
    n.location = loc
    nt.links.new(a, n.inputs[0])
    if b is not None:
        nt.links.new(b, n.inputs[1])
    if scale is not None:
        nt.links.new(scale, n.inputs[3])
    return n.outputs["Value"] if op in ("DISTANCE", "LENGTH", "DOT_PRODUCT") else n.outputs["Vector"]


def build_node_group():
    ng = bpy.data.node_groups.new("ChronoShards", "GeometryNodeTree")
    io = ng.interface
    io.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    io.new_socket("World Time", in_out="INPUT", socket_type="NodeSocketFloat")
    io.new_socket("Pulse", in_out="INPUT", socket_type="NodeSocketObject")
    io.new_socket("Shards", in_out="INPUT", socket_type="NodeSocketCollection")
    io.new_socket("Sigma", in_out="INPUT", socket_type="NodeSocketFloat")
    io.new_socket("Explode K", in_out="INPUT", socket_type="NodeSocketFloat")
    io.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nt = ng
    gi = nt.nodes.new("NodeGroupInput")
    gi.location = (-1800, 0)
    go = nt.nodes.new("NodeGroupOutput")
    go.location = (1400, 0)
    Tw = gi.outputs["World Time"]

    a = {k: _attr_node(nt, k, d, (-1500, -i * 60)) for i, (k, (_, d)) in enumerate(ATTRS.items())}
    tau_raw = _math(nt, "SUBTRACT", Tw, a["p_trig"], (-1200, 300))
    visible = _math(nt, "GREATER_THAN", tau_raw, 0.0, (-1000, 400))
    tau = _math(nt, "MULTIPLY", _math(nt, "MAXIMUM", tau_raw, 0.0, (-1100, 300)), a["p_gain"], (-1000, 300))
    neg = _math(nt, "MULTIPLY", tau, gi.outputs["Explode K"], (-900, 300))
    env = _math(nt, "SUBTRACT", 1.0, _math(nt, "EXPONENT", _math(nt, "MULTIPLY", neg, -1.0, (-800, 300)),
                                            None, (-700, 300)), (-600, 300))
    # drift: A (sin(w Tw + phi) - sin(w trig + phi)) * visible
    s1 = _math(nt, "SINE", _math(nt, "ADD", _math(nt, "MULTIPLY", a["p_omega"], Tw, (-1100, 0)),
                                 a["p_phase"], (-1000, 0)), None, (-900, 0))
    s0 = _math(nt, "SINE", _math(nt, "ADD", _math(nt, "MULTIPLY", a["p_omega"], a["p_trig"], (-1100, -100)),
                                 a["p_phase"], (-1000, -100)), None, (-900, -100))
    drift = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", s1, s0, (-800, 0)), visible, (-700, 0))
    offset = _vmath(nt, "ADD", _vmath(nt, "SCALE", a["p_dir"], scale=env, loc=(-500, 200)),
                    _vmath(nt, "SCALE", a["p_amp"], scale=drift, loc=(-500, 0)), loc=(-350, 100))

    setpos = nt.nodes.new("GeometryNodeSetPosition")
    setpos.location = (-150, 0)
    nt.links.new(gi.outputs["Geometry"], setpos.inputs["Geometry"])
    nt.links.new(offset, setpos.inputs["Offset"])

    # distortion field glow from the pulse's evaluated position
    oi = nt.nodes.new("GeometryNodeObjectInfo")
    oi.location = (-500, -400)
    oi.transform_space = "ORIGINAL"
    nt.links.new(gi.outputs["Pulse"], oi.inputs["Object"])
    pos = nt.nodes.new("GeometryNodeInputPosition")
    pos.location = (-500, -250)
    d = _vmath(nt, "DISTANCE", pos.outputs["Position"], oi.outputs["Location"], loc=(-300, -300))
    sig2 = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", gi.outputs["Sigma"], gi.outputs["Sigma"], (-300, -450)),
                 -2.0, (-200, -450))
    D = _math(nt, "EXPONENT", _math(nt, "DIVIDE", _math(nt, "MULTIPLY", d, d, (-200, -300)), sig2, (-100, -350)),
              None, (0, -350))
    flash = _math(nt, "MULTIPLY", _math(nt, "EXPONENT", _math(nt, "MULTIPLY", tau, -3.0, (-100, -550)),
                                        None, (0, -550)), _math(nt, "MULTIPLY", visible, 0.5, (0, -650)), (100, -550))
    glow = _math(nt, "MAXIMUM", _math(nt, "MULTIPLY", D, D, (100, -350)), flash, (200, -400))
    store = nt.nodes.new("GeometryNodeStoreNamedAttribute")
    store.location = (300, 0)
    store.data_type = "FLOAT"
    store.domain = "POINT"
    store.inputs["Name"].default_value = "glow"
    nt.links.new(setpos.outputs["Geometry"], store.inputs["Geometry"])
    nt.links.new(glow, store.inputs["Value"])

    # orientation: seeded base euler, then spin about a seeded axis as the burst unfolds
    e2r = nt.nodes.new("FunctionNodeEulerToRotation")
    e2r.location = (300, 300)
    nt.links.new(a["p_rot0"], e2r.inputs["Euler"])
    ang = _math(nt, "MULTIPLY", a["p_spin"], _math(nt, "ADD", env, _math(nt, "MULTIPLY", Tw, 0.15, (200, 500)),
                                                  (300, 500)), (400, 500))
    aa = nt.nodes.new("FunctionNodeAxisAngleToRotation")
    aa.location = (500, 400)
    nt.links.new(a["p_axis"], aa.inputs["Axis"])
    nt.links.new(ang, aa.inputs["Angle"])
    rr = nt.nodes.new("FunctionNodeRotateRotation")
    rr.location = (700, 300)
    rr.rotation_space = "LOCAL"
    nt.links.new(e2r.outputs["Rotation"], rr.inputs["Rotation"])
    nt.links.new(aa.outputs["Rotation"], rr.inputs["Rotate By"])

    ci = nt.nodes.new("GeometryNodeCollectionInfo")
    ci.location = (700, -200)
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    nt.links.new(gi.outputs["Shards"], ci.inputs["Collection"])
    iop = nt.nodes.new("GeometryNodeInstanceOnPoints")
    iop.location = (1000, 0)
    nt.links.new(store.outputs["Geometry"], iop.inputs["Points"])
    nt.links.new(ci.outputs["Instances"], iop.inputs["Instance"])
    iop.inputs["Pick Instance"].default_value = True
    nt.links.new(a["p_variant"], iop.inputs["Instance Index"])
    nt.links.new(rr.outputs["Rotation"], iop.inputs["Rotation"])
    nt.links.new(_math(nt, "MULTIPLY", a["p_scale"], visible, (800, -400)), iop.inputs["Scale"])
    nt.links.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


def build_fragments(cfg, tl, frags, pulse, mats):
    col = collection("Fragments")
    arche = shard_archetypes(cfg["seed"], mats["shard"])
    n = len(frags["origin"])
    me = bpy.data.meshes.new("ShardField")
    me.vertices.add(n)
    me.vertices.foreach_set("co", frags["origin"].astype(np.float32).ravel())
    for name, (key, dtype) in ATTRS.items():
        attr = me.attributes.new(name, dtype, "POINT")
        data = frags[key]
        if dtype == "FLOAT_VECTOR":
            attr.data.foreach_set("vector", data.astype(np.float32).ravel())
        elif dtype == "INT":
            attr.data.foreach_set("value", data.astype(np.int32))
        else:
            attr.data.foreach_set("value", data.astype(np.float32))
    obj = bpy.data.objects.new("ShardField", me)
    col.objects.link(obj)
    ng = build_node_group()
    mod = obj.modifiers.new("Shards", "NODES")
    mod.node_group = ng
    ids = {it.name: it.identifier for it in ng.interface.items_tree
           if it.item_type == "SOCKET" and it.in_out == "INPUT"}
    inputs = mod.properties.inputs  # Blender 5.x modifier interface
    getattr(inputs, ids["Pulse"]).value = pulse
    getattr(inputs, ids["Shards"]).value = arche
    getattr(inputs, ids["Sigma"]).value = float(cfg["distortion"]["sigma"])
    getattr(inputs, ids["Explode K"]).value = float(cfg["fragments"]["explode_k"])
    ft = tl.frame_tables()
    keyframes(obj, f'modifiers["Shards"].properties.inputs.{ids["World Time"]}.value', tl.frames, ft["world_time"])
    obj["shard_count"] = n
    return obj
