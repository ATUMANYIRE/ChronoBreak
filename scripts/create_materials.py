"""Procedural materials: circular-grained titanium/brass, blued steel, obsidian, energy."""
import bpy

AMBER = (1.0, 0.46, 0.09, 1.0)
GOLD = (1.0, 0.66, 0.26, 1.0)
WHITE_HOT = (1.0, 0.86, 0.66, 1.0)
TITANIUM = (0.62, 0.63, 0.66, 1.0)
BRASS = (0.86, 0.6, 0.3, 1.0)
BLUED = (0.035, 0.04, 0.06, 1.0)


def _new(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    return mat, nt, out


def metal(name, color, rough=0.26, ring_scale=34.0, glow_from_object=True):
    """Metal with concentric 'circular graining' driven by a rings wave texture in object space.

    The object's colour channel R carries the distortion field D(x,t) of the gear,
    keyed per frame, which adds a faint amber inner glow when the pulse passes.
    """
    mat, nt, out = _new(name)
    n, l = nt.nodes, nt.links
    bsdf = n.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = 1.0
    tc = n.new("ShaderNodeTexCoord")
    tc.location = (-900, 0)
    wave = n.new("ShaderNodeTexWave")
    wave.location = (-650, 100)
    wave.wave_type = "RINGS"
    wave.rings_direction = "Z"
    wave.inputs["Scale"].default_value = ring_scale
    wave.inputs["Distortion"].default_value = 1.2
    wave.inputs["Detail"].default_value = 3.0
    noise = n.new("ShaderNodeTexNoise")
    noise.location = (-650, -150)
    noise.inputs["Scale"].default_value = 3.0
    l.new(tc.outputs["Object"], wave.inputs["Vector"])
    l.new(tc.outputs["Object"], noise.inputs["Vector"])
    mix = n.new("ShaderNodeMath")
    mix.location = (-400, 50)
    mix.operation = "MULTIPLY_ADD"
    l.new(wave.outputs["Fac"], mix.inputs[0])
    mix.inputs[1].default_value = 0.6
    l.new(noise.outputs["Fac"], mix.inputs[2])
    ramp = n.new("ShaderNodeMapRange")
    ramp.location = (-200, 50)
    ramp.inputs["From Min"].default_value = 0.2
    ramp.inputs["From Max"].default_value = 1.4
    ramp.inputs["To Min"].default_value = rough * 0.6
    ramp.inputs["To Max"].default_value = rough * 1.45
    l.new(mix.outputs[0], ramp.inputs["Value"])
    l.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
    bump = n.new("ShaderNodeBump")
    bump.location = (0, -200)
    bump.inputs["Strength"].default_value = 0.05
    l.new(wave.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if glow_from_object:
        oi = n.new("ShaderNodeObjectInfo")
        oi.location = (-200, -400)
        sep = n.new("ShaderNodeSeparateColor")
        sep.location = (0, -400)
        l.new(oi.outputs["Color"], sep.inputs["Color"])
        bsdf.inputs["Emission Color"].default_value = AMBER
        sc = n.new("ShaderNodeMath")
        sc.operation = "MULTIPLY"
        sc.location = (150, -400)
        sc.inputs[1].default_value = 1.6
        l.new(sep.outputs["Red"], sc.inputs[0])
        l.new(sc.outputs[0], bsdf.inputs["Emission Strength"])
    l.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def obsidian(name="Obsidian"):
    mat, nt, out = _new(name)
    n, l = nt.nodes, nt.links
    bsdf = n.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.004, 0.004, 0.005, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.45
    bsdf.inputs["Coat Weight"].default_value = 0.35
    bsdf.inputs["Coat Roughness"].default_value = 0.28
    tc = n.new("ShaderNodeTexCoord")
    wave = n.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.rings_direction = "Z"
    wave.inputs["Scale"].default_value = 0.6
    wave.inputs["Distortion"].default_value = 0.0
    l.new(tc.outputs["Object"], wave.inputs["Vector"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    l.new(wave.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    l.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def emission(name, color, strength):
    mat, nt, out = _new(name)
    em = nt.nodes.new("ShaderNodeEmission")
    em.name = "Emission"
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def halo(name="PulseHalo"):
    """Soft spherical glow: emission fading towards the silhouette, alpha-blended."""
    mat, nt, out = _new(name)
    n, l = nt.nodes, nt.links
    lw = n.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    pw = n.new("ShaderNodeMath")
    pw.operation = "POWER"
    inv = n.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    l.new(lw.outputs["Facing"], inv.inputs[1])
    l.new(inv.outputs[0], pw.inputs[0])
    pw.inputs[1].default_value = 4.0
    em = n.new("ShaderNodeEmission")
    em.name = "Emission"
    em.inputs["Color"].default_value = AMBER
    em.inputs["Strength"].default_value = 3.0
    tr = n.new("ShaderNodeBsdfTransparent")
    mix = n.new("ShaderNodeMixShader")
    l.new(pw.outputs[0], mix.inputs["Fac"])
    l.new(tr.outputs[0], mix.inputs[1])
    l.new(em.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    mat.use_transparency_overlap = False
    return mat


def shard_material(name="Shard"):
    """Instanced shard surface: tint and glow come from the Geometry Nodes instancer."""
    mat, nt, out = _new(name)
    n, l = nt.nodes, nt.links
    bsdf = n.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.13
    tint = n.new("ShaderNodeAttribute")
    tint.attribute_type = "INSTANCER"
    tint.attribute_name = "p_tint"
    ramp = n.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0.0
    cr.elements[0].color = TITANIUM
    cr.elements[1].position = 0.25
    cr.elements[1].color = BRASS
    e = cr.elements.new(0.75)
    e.color = BLUED
    div = n.new("ShaderNodeMath")
    div.operation = "MULTIPLY"
    div.inputs[1].default_value = 0.5
    l.new(tint.outputs["Fac"], div.inputs[0])
    l.new(div.outputs[0], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    glow = n.new("ShaderNodeAttribute")
    glow.attribute_type = "INSTANCER"
    glow.attribute_name = "glow"
    gm = n.new("ShaderNodeMath")
    gm.operation = "MULTIPLY"
    gm.inputs[1].default_value = 3.0
    l.new(glow.outputs["Fac"], gm.inputs[0])
    bsdf.inputs["Emission Color"].default_value = AMBER
    l.new(gm.outputs[0], bsdf.inputs["Emission Strength"])
    l.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build_materials():
    return {
        "titanium": metal("BrushedTitanium", TITANIUM, 0.24),
        "brass": metal("CircularBrass", BRASS, 0.22),
        "blued": metal("BluedSteel", BLUED, 0.2, ring_scale=60.0),
        "titanium_static": metal("TitaniumStatic", TITANIUM, 0.2, glow_from_object=False),
        "obsidian": obsidian(),
        "pulse_core": emission("PulseCore", WHITE_HOT, 60.0),
        "pulse_halo": halo(),
        "streak": emission("Streak", AMBER, 18.0),
        "hand": emission("SecondHand", GOLD, 4.0),
        "lume": emission("DialLume", GOLD, 0.0),
        "title": emission("Title", GOLD, 0.0),
        "shard": shard_material(),
    }
