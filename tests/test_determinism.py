import copy

import numpy as np

import animation_math as am
import procedural as pr


def _layout(seed=None):
    cfg = am.load_config("scene.json")
    if seed is not None:
        cfg = copy.deepcopy(cfg)
        cfg["seed"] = seed
    return pr.build_layout(cfg)


def test_layout_is_reproducible():
    _, _, g1, f1 = _layout()
    _, _, g2, f2 = _layout()
    assert len(g1) == len(g2)
    for a, b in zip(g1, g2):
        assert np.array_equal(a["center"], b["center"])
        assert a["teeth"] == b["teeth"] and a["fracture_t"] == b["fracture_t"]
    for k in f1:
        assert np.array_equal(f1[k], f2[k]), k


def test_different_seed_changes_layout():
    _, _, _, f1 = _layout()
    _, _, _, f2 = _layout(seed=7)
    assert not np.array_equal(f1["origin"][:50], f2["origin"][:50])


def test_shard_archetypes_reproducible():
    a = [pr.shard_points(np.random.default_rng(5)) for _ in range(2)]
    assert np.array_equal(a[0], a[1])


def test_gear_mesh_is_valid_and_reproducible():
    for arch in pr.GEAR_ARCHETYPES:
        v, f = pr.gear_mesh(arch["teeth"], arch["spokes"])
        v2, f2 = pr.gear_mesh(arch["teeth"], arch["spokes"])
        assert v == v2 and f == f2
        assert all(0 <= i < len(v) for face in f for i in face)
        r = np.hypot(np.array(v)[:, 0], np.array(v)[:, 1])
        assert r.max() <= arch["teeth"] / 2 + 1.0 + 1e-9


def test_meshing_gears_have_consistent_ratios():
    _, _, gears, _ = _layout()
    by_train = {}
    for g in gears:
        by_train.setdefault(g["train"], []).append(g)
    for members in by_train.values():
        for a, b in zip(members, members[1:]):
            dist = np.hypot(*(a["center"][:2] - b["center"][:2]))
            assert abs(dist - (a["teeth"] + b["teeth"]) / 2 * a["module"]) < 1e-9
            assert b["ratio"] == -a["ratio"] * a["teeth"] / b["teeth"]
