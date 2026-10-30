"""Run inside interactive Blender (not -b): arrange a WIP layout and save a real UI screenshot."""
import os

import bpy

OUT = os.environ["CHRONO_SCREENSHOT"]
FRAME = int(os.environ.get("CHRONO_SCREENSHOT_FRAME", "380"))


def arrange():
    scene = bpy.context.scene
    scene.frame_set(FRAME)
    shard = bpy.data.objects["ShardField"]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    shard.select_set(True)
    bpy.context.view_layer.objects.active = shard
    # the stock Geometry Nodes workspace: viewport + spreadsheet + node editor showing ChronoShards
    ws = bpy.data.workspaces.get("Geometry Nodes")
    if ws is not None:
        bpy.context.window.workspace = ws
    return None


def frame_views():
    screen = bpy.context.window.screen
    for area in screen.areas:
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is None:
            continue
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.shading.type = "MATERIAL"
            space.overlay.show_overlays = True
            with bpy.context.temp_override(area=area, region=region):
                if space.region_3d.view_perspective != "CAMERA":
                    bpy.ops.view3d.view_camera()
        elif area.type == "NODE_EDITOR":
            area.spaces.active.node_tree = bpy.data.node_groups["ChronoShards"]
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.node.view_all()
    return None


def quit_blender():
    bpy.ops.wm.quit_blender()
    return None


def shoot():
    bpy.ops.screen.screenshot(filepath=OUT)
    print("SCREENSHOT", OUT, flush=True)
    bpy.app.timers.register(quit_blender, first_interval=1.0)
    return None


bpy.app.timers.register(arrange, first_interval=2.0)
bpy.app.timers.register(frame_views, first_interval=8.0)
bpy.app.timers.register(shoot, first_interval=25.0)
