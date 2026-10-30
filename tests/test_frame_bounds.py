import numpy as np

import animation_math as am
import procedural as pr


def test_duration_and_frame_count():
    cfg = am.load_config("scene.json")
    tl = am.Timeline(cfg)
    assert cfg["frame_end"] - cfg["frame_start"] + 1 == 576 and cfg["fps"] == 24
    assert tl.duration == 24.0
    assert 5.0 <= tl.duration <= 30.0
    assert tl.frame_to_time(cfg["frame_start"]) == 0.0


def test_render_config():
    r = am.load_config("render.json")
    assert r["presets"]["final"]["resolution"] == [1920, 1080]
    assert r["engine"] == "BLENDER_EEVEE"


def test_timeline_events_inside_animation():
    cfg = am.load_config("scene.json")
    tm = cfg["timing"]
    duration = (cfg["frame_end"] - cfg["frame_start"] + 1) / cfg["fps"]
    order = [tm["awaken_start"], tm["pulse_start"], tm["world_slow_start"], tm["bullet_in"][0],
             tm["bullet_out"][1], tm["pulse_arrive"], tm["reveal_end"], tm["tick_time"], tm["title_in"][1]]
    assert order == sorted(order)
    assert order[-1] < duration


def test_all_frame_tables_finite():
    tl = am.Timeline(am.load_config("scene.json"))
    ft = tl.frame_tables()
    assert len(ft["frame"]) == 576
    for k, v in ft.items():
        assert np.all(np.isfinite(v)), k


def test_shards_and_gears_inside_clock():
    cfg = am.load_config("scene.json")
    _, _, gears, fr = pr.build_layout(cfg)
    assert len(gears) >= 80
    limit = cfg["clock"]["radius_inner_mechanism"] + 1e-9
    assert all(np.hypot(*g["center"][:2]) + g["radius"] <= limit for g in gears)
    assert np.all(np.isfinite(fr["origin"]))
    assert np.all(np.hypot(fr["origin"][:, 0], fr["origin"][:, 1]) < cfg["clock"]["bezel_radius"])
    assert sum(g["fracture_t"] is not None for g in gears) >= 5
