"""Compositing: bloom, subtle lens dispersion and a soft vignette (Blender 5.x node groups)."""
import bpy


def build_compositor(scene):
    ng = bpy.data.node_groups.new("ChronoComp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    scene.compositing_node_group = ng
    n, l = ng.nodes, ng.links
    rl = n.new("CompositorNodeRLayers")
    rl.location = (-800, 0)
    glare = n.new("CompositorNodeGlare")
    glare.location = (-500, 0)
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 1.0
    glare.inputs["Strength"].default_value = 0.65
    glare.inputs["Size"].default_value = 0.75
    l.new(rl.outputs["Image"], glare.inputs["Image"])
    lens = n.new("CompositorNodeLensdist")
    lens.location = (-250, 0)
    lens.inputs["Dispersion"].default_value = 0.012
    lens.inputs["Distortion"].default_value = 0.0
    l.new(glare.outputs["Image"], lens.inputs["Image"])
    ell = n.new("CompositorNodeEllipseMask")
    ell.location = (-500, -300)
    ell.inputs["Size"].default_value = (0.92, 0.95)
    ell.inputs["Mask"].default_value = 0.0
    ell.inputs["Value"].default_value = 1.0
    blur = n.new("CompositorNodeBlur")
    blur.name = "VignetteBlur"
    blur.location = (-250, -300)
    blur.inputs["Size"].default_value = (260, 260)
    blur.inputs["Type"].default_value = "Gaussian"
    l.new(ell.outputs["Mask"], blur.inputs["Image"])
    lift = n.new("ShaderNodeMapRange")
    lift.location = (0, -300)
    lift.inputs["To Min"].default_value = 0.55
    l.new(blur.outputs["Image"], lift.inputs["Value"])
    mix = n.new("ShaderNodeMix")
    mix.location = (250, 0)
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    l.new(lens.outputs["Image"], mix.inputs[6])
    l.new(lift.outputs["Result"], mix.inputs[7])
    out = n.new("NodeGroupOutput")
    out.location = (500, 0)
    l.new(mix.outputs[2], out.inputs["Image"])
    return ng
