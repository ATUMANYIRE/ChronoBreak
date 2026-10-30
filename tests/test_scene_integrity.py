"""Runs the Blender-side integrity check on the built .blend (skipped if Blender/.blend absent)."""
import json
import os
import subprocess

import pytest

import animation_math as am

RCFG = am.load_config("render.json")
BLENDER = RCFG["blender_exe"]
BLEND = os.path.join(am.ROOT, RCFG["blend_file"])


@pytest.mark.skipif(not (os.path.exists(BLENDER) and os.path.exists(BLEND)), reason="Blender or .blend not available")
def test_scene_integrity():
    script = os.path.join(am.ROOT, "scripts", "verify_output.py")
    res = subprocess.run([BLENDER, "-b", BLEND, "--python", script, "--", "scene"],
                         capture_output=True, text=True, timeout=600)
    line = next(ln for ln in res.stdout.splitlines() if ln.startswith("SCENE_REPORT "))
    report = json.loads(line[len("SCENE_REPORT "):])
    assert report["errors"] == []
    assert report["frames"] == [1, 576] and report["fps"] == 24
    assert report["engine"] == "BLENDER_EEVEE"
    assert report["gears"] >= 80 and report["fractured_gears"] >= 5
    assert report["shard_instances_at_400"] > 3000
