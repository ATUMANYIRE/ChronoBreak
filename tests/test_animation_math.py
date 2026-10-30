import math

import numpy as np
import pytest

import animation_math as am


@pytest.fixture(scope="module")
def tl():
    return am.Timeline(am.load_config("scene.json"))


def test_bezier_endpoints_and_formula():
    ctrl = np.array([[0, 0, 0], [1, 2, 0], [3, 2, 1], [4, 0, 0]], float)
    assert np.allclose(am.bezier(ctrl, 0.0), ctrl[0])
    assert np.allclose(am.bezier(ctrl, 1.0), ctrl[3])
    u = 0.3
    w = 1 - u
    expect = w ** 3 * ctrl[0] + 3 * w ** 2 * u * ctrl[1] + 3 * w * u ** 2 * ctrl[2] + u ** 3 * ctrl[3]
    assert np.allclose(am.bezier(ctrl, u), expect)


def test_arc_length_matches_gauss_legendre(tl):
    x, w = np.polynomial.legendre.leggauss(64)
    u = 0.5 * (x + 1)
    speed = np.linalg.norm(am.bezier_derivative(tl.ctrl, u), axis=1)
    exact = 0.5 * np.sum(w * speed)
    assert tl.path.length == pytest.approx(exact, rel=1e-5)


def test_arc_length_parameterisation_is_uniform(tl):
    s = np.linspace(0, tl.path.length, 401)
    pts = tl.path.point(s)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    assert seg.max() / seg.min() < 1.01  # equal arc steps give equal chords
    assert np.all(np.diff(tl.path.u_at(s)) > 0)


def test_raw_parameter_is_not_distance(tl):
    """The raw Bezier parameter is visibly non-uniform, which is why the arc-length table exists."""
    pts = am.bezier(tl.ctrl, np.linspace(0, 1, 401))
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    assert seg.max() / seg.min() > 1.2


def test_progress_bounds_and_monotonic(tl):
    p = tl.frame_tables()["progress"]
    assert p[0] == 0.0
    assert np.all(np.diff(p) >= -1e-12)
    tm = tl.tm
    assert tl.progress(tm["pulse_start"] - 0.01) == 0.0
    assert tl.progress(tm["pulse_arrive"]) == pytest.approx(1.0, abs=2e-3)
    assert tl.progress(23.9) == 1.0


def test_velocity_profile_is_derivative_of_displacement(tl):
    tm = tl.tm
    tau = np.linspace(tm["pulse_start"] + 0.5, tm["pulse_start"] + 8.0, 9)
    h = 1e-5
    num = (tl.progress_from_story(tau + h) - tl.progress_from_story(tau - h)) / (2 * h) * tl.path.length
    assert np.allclose(num, tl.speed_from_story(tau), rtol=1e-4)
    x = tau - tm["pulse_start"]
    v = tm["v0"] + tm["accel_a"] * x ** tm["accel_p"]
    ratio = tl.speed_from_story(tau) / v
    assert np.allclose(ratio, ratio[0])  # exactly v(t) = v0 + a t^p up to normalisation
    assert np.all(np.diff(tl.speed_from_story(tau)) > 0)  # accelerating


def test_distortion_field():
    p = np.array([1.0, 2.0, 3.0])
    assert am.distortion(p, p, 5.0) == pytest.approx(1.0)
    assert am.distortion(p + [5.0, 0, 0], p, 5.0) == pytest.approx(math.exp(-0.5))
    assert 0 <= am.distortion(p + [100.0, 0, 0], p, 5.0) < 1e-50


def test_cumulative_equals_independent_integral(tl):
    g = tl.grid_tables()
    for frame in (1, 97, 250, 401, 576):
        t = float(tl.frame_to_time(frame))
        i = int(round(t * am.INTEGRATION_STEPS_PER_SECOND))
        assert g["world_time"][i] == pytest.approx(tl.world_time(t), abs=1e-9)
        assert g["story_time"][i] == pytest.approx(tl.story_time(t), abs=1e-9)


def test_world_slows_while_pulse_speeds_up(tl):
    tm = tl.tm
    assert tl.world_rate(2.0) == pytest.approx(1.0)
    assert tl.world_rate(17.0) == pytest.approx(tm["world_rate_min"])
    assert tl.world_rate(23.5) == pytest.approx(1.0)
    ft = tl.frame_tables()
    i9, i15 = 9 * 24, 15 * 24
    assert ft["speed"][i15] > 3 * ft["speed"][i9]
    assert ft["world_rate"][i15] < 0.1 * ft["world_rate"][i9]


def test_gear_angle_cumulative_matches_single(tl):
    c = np.array([[20.0, 12.0, 14.0], [-40.0, 10.0, 4.0]])
    om = np.array([0.7, -1.1])
    times = tl.frame_to_time(np.array([1, 200, 333, 576]))
    a = am.gear_train_angles(tl, c, om, 0.92, times)
    for gi in range(2):
        for ti, t in enumerate(times):
            single = am.gear_train_angle_single(tl, c[gi], om[gi], 0.92, float(t))
            assert a[gi, ti] == pytest.approx(single, abs=1e-7)


def test_tick_angle():
    assert am.tick_angle(1.0, 2.0, 6.0) == 0.0
    assert am.tick_angle(5.0, 2.0, 6.0) == pytest.approx(-math.radians(6.0), abs=1e-9)
    assert np.min(am.tick_angle(np.linspace(2, 3, 500), 2.0, 6.0)) < -math.radians(6.0)  # overshoot


def test_fragment_offset_envelope_bounded():
    d = np.array([[2.0, 0, 0]])
    amp = np.array([[0.1, 0.2, 0.0]])
    args = (np.array([5.0]), np.array([1.0]), 2.4, amp, np.array([1.3]), np.array([0.4]))
    assert np.allclose(am.fragment_offset(d, *args[:1], *args[1:], 4.0), 0.0)
    assert np.allclose(am.fragment_offset(d, *args[:1], *args[1:], 5.0), 0.0)
    late = am.fragment_offset(d, *args[:1], *args[1:], 1e4)
    assert np.linalg.norm(late) <= np.linalg.norm(d) + 2 * np.linalg.norm(amp) + 1e-9


def test_path_projects_to_straight_second_hand(tl):
    """Every path point lies in the vertical plane through the clock axis at the hand angle,
    so the top-down camera on the axis sees a straight radial line."""
    pts = tl.path.point(np.linspace(0, tl.path.length, 500))
    radial = tl.clock.radial
    cross = pts[:, 0] * radial[1] - pts[:, 1] * radial[0]
    assert np.max(np.abs(cross)) < 1e-9
    assert np.all(pts[:, :2] @ radial[:2] > 0)


def test_camera_states_are_finite_and_orthonormal(tl):
    rig = am.CameraRig(tl)
    ft = tl.frame_tables()
    for i in range(0, len(ft["t"]), 3):
        st = rig.state(float(ft["t"][i]), ft["pos"][i], ft["s"][i])
        for k in ("pos", "target", "up"):
            assert np.all(np.isfinite(st[k]))
        m = am.look_at_matrix(st["pos"], st["target"], st["up"])
        assert np.allclose(m.T @ m, np.eye(3), atol=1e-9)
        assert np.linalg.det(m) == pytest.approx(1.0)
        assert 10 <= st["lens"] <= 40
        assert st["focus"] > 0
    end = rig.state(float(ft["t"][-1]), ft["pos"][-1], ft["s"][-1])
    assert np.allclose(end["pos"], [0, 0, rig.top_height], atol=1e-6)


def test_camera_motion_is_continuous(tl):
    """Single take: no frame-to-frame jump larger than the fastest designed move."""
    rig = am.CameraRig(tl)
    ft = tl.frame_tables()
    pos = np.array([rig.state(float(t), ft["pos"][i], ft["s"][i])["pos"] for i, t in enumerate(ft["t"])])
    step = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    assert np.all(np.isfinite(step))
    assert step.max() < 12.0
