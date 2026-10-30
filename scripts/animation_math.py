"""Deterministic animation mathematics for CHRONOBREAK.

Pure Python + NumPy (no bpy), so it is importable both inside Blender and by
pytest. Every quantity is a pure function of time t (seconds, frame 1 -> t=0);
nothing depends on previously evaluated frames.

Clocks
------
real time      t           the viewer's clock (frames / fps)
story time     tau(t)      = integral of story_rate; dips during the bullet-time beat
world time     T_w(t)      = integral of world_rate; the environment's clock, which
                             slows as the pulse accelerates (the core idea)
pulse progress f(t)        normalised displacement of v(x) = v0 + a x^p over story time
"""
import json
import math
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTEGRATION_STEPS_PER_SECOND = 240  # 10 sub-steps per frame at 24 fps


def load_config(name):
    with open(os.path.join(ROOT, "config", name), "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- easing ---

def smoothstep(e0, e1, x):
    x = np.clip((np.asarray(x, dtype=float) - e0) / (e1 - e0), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def smootherstep(e0, e1, x):
    x = np.clip((np.asarray(x, dtype=float) - e0) / (e1 - e0), 0.0, 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


def pchip(xk, yk, x):
    """Monotone cubic Hermite interpolation (Fritsch-Carlson). Clamped at the ends."""
    xk = np.asarray(xk, dtype=float)
    yk = np.asarray(yk, dtype=float)
    x = np.clip(np.asarray(x, dtype=float), xk[0], xk[-1])
    h = np.diff(xk)
    delta = np.diff(yk) / h
    m = np.zeros_like(yk)
    for i in range(1, len(xk) - 1):
        if delta[i - 1] * delta[i] > 0.0:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    idx = np.clip(np.searchsorted(xk, x, side="right") - 1, 0, len(xk) - 2)
    hh = h[idx]
    s = (x - xk[idx]) / hh
    h00 = (1 + 2 * s) * (1 - s) ** 2
    h10 = s * (1 - s) ** 2
    h01 = s * s * (3 - 2 * s)
    h11 = s * s * (s - 1)
    return h00 * yk[idx] + h10 * hh * m[idx] + h01 * yk[idx + 1] + h11 * hh * m[idx + 1]


# ---------------------------------------------------------------- bezier ---

def bezier(ctrl, u):
    """B(u) = (1-u)^3 P0 + 3(1-u)^2 u P1 + 3(1-u) u^2 P2 + u^3 P3."""
    p = np.asarray(ctrl, dtype=float)
    u = np.asarray(u, dtype=float)[..., None]
    w = 1.0 - u
    return w ** 3 * p[0] + 3 * w ** 2 * u * p[1] + 3 * w * u ** 2 * p[2] + u ** 3 * p[3]


def bezier_derivative(ctrl, u):
    p = np.asarray(ctrl, dtype=float)
    u = np.asarray(u, dtype=float)[..., None]
    w = 1.0 - u
    return 3 * w ** 2 * (p[1] - p[0]) + 6 * w * u * (p[2] - p[1]) + 3 * u ** 2 * (p[3] - p[2])


class ArcLengthBezier:
    """Cubic Bezier re-parameterised by arc length s via a dense chord-length table."""

    def __init__(self, ctrl, samples=8192):
        self.ctrl = np.asarray(ctrl, dtype=float)
        self._u = np.linspace(0.0, 1.0, samples + 1)
        pts = bezier(self.ctrl, self._u)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        self._s = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self._s[-1])

    def u_at(self, s):
        return np.interp(np.clip(s, 0.0, self.length), self._s, self._u)

    def point(self, s):
        return bezier(self.ctrl, self.u_at(s))

    def tangent(self, s):
        d = bezier_derivative(self.ctrl, self.u_at(s))
        return d / np.linalg.norm(d, axis=-1, keepdims=True)


# ------------------------------------------------------------ clock frame ---

class ClockFrame:
    """Clock dial lies in the XY plane, 12 o'clock = +Y, angles clockwise seen from +Z.

    The pulse path lives in the vertical plane through the clock axis at the second
    hand's angle, so from a camera on the axis the whole curved 3D path projects to a
    straight radial line: the second hand.
    """

    def __init__(self, hand_angle_deg):
        a = math.radians(hand_angle_deg)
        self.radial = np.array([math.sin(a), math.cos(a), 0.0])
        self.side = np.array([math.cos(a), -math.sin(a), 0.0])
        self.up = np.array([0.0, 0.0, 1.0])

    def rh_to_world(self, rh):
        rh = np.asarray(rh, dtype=float)
        return rh[..., 0:1] * self.radial + rh[..., 1:2] * self.up


def clock_direction(angle_deg):
    a = math.radians(angle_deg)
    return np.array([math.sin(a), math.cos(a), 0.0])


# ------------------------------------------------------------ integration ---

def integrate_rate(rate_fn, t, per_second=INTEGRATION_STEPS_PER_SECOND):
    """Integral of rate_fn over [0, t] on a fixed grid (trapezoid). Pure function of t."""
    t = float(t)
    if t <= 0.0:
        return 0.0
    n = max(1, int(math.ceil(t * per_second - 1e-9)))
    x = np.linspace(0.0, t, n + 1)
    y = rate_fn(x)
    return float(np.sum((y[1:] + y[:-1]) * 0.5 * np.diff(x)))


def cumulative_grid(t_max, per_second=INTEGRATION_STEPS_PER_SECOND):
    n = max(1, int(math.ceil(t_max * per_second - 1e-9)))
    return np.linspace(0.0, n / per_second, n + 1)


def cumulative_trapezoid(y, x, axis=-1):
    y = np.asarray(y, dtype=float)
    dx = np.diff(x)
    a = np.moveaxis(y, axis, -1)
    inc = (a[..., 1:] + a[..., :-1]) * 0.5 * dx
    out = np.concatenate([np.zeros(a.shape[:-1] + (1,)), np.cumsum(inc, axis=-1)], axis=-1)
    return np.moveaxis(out, -1, axis)


# -------------------------------------------------------------- distortion ---

def distortion(x, p, sigma):
    """D(x,t) = exp(-||x - P(t)||^2 / (2 sigma^2))."""
    d2 = np.sum((np.asarray(x, dtype=float) - np.asarray(p, dtype=float)) ** 2, axis=-1)
    return np.exp(-d2 / (2.0 * sigma * sigma))


# ---------------------------------------------------------------- timeline ---

class Timeline:
    def __init__(self, cfg):
        self.cfg = cfg
        self.fps = cfg["fps"]
        self.frame_start = cfg["frame_start"]
        self.frame_end = cfg["frame_end"]
        tm = cfg["timing"]
        self.tm = tm
        self.clock = ClockFrame(cfg["clock"]["hand_angle_deg"])
        self.ctrl = self.clock.rh_to_world(cfg["path"]["control_rh"])
        self.path = ArcLengthBezier(self.ctrl)
        self.sigma = cfg["distortion"]["sigma"]
        self._x_end = self.story_time(tm["pulse_arrive"]) - tm["pulse_start"]
        self._disp_end = self._disp(self._x_end)

    # time base
    def frame_to_time(self, frame):
        return (np.asarray(frame, dtype=float) - self.frame_start) / self.fps

    @property
    def frames(self):
        return np.arange(self.frame_start, self.frame_end + 1)

    @property
    def duration(self):
        return (self.frame_end - self.frame_start + 1) / self.fps

    # world clock: slows from 1 to rate_min while the pulse accelerates, resumes at the reveal
    def world_rate(self, t):
        tm = self.tm
        drop = 1.0 - tm["world_rate_min"]
        return (1.0 - drop * smoothstep(tm["world_slow_start"], tm["world_slow_end"], t)
                + drop * smoothstep(tm["world_resume_start"], tm["world_resume_end"], t))

    def world_time(self, t):
        return integrate_rate(self.world_rate, t)

    # story clock: the bullet-time beat freezes even the pulse for a moment
    def story_rate(self, t):
        tm = self.tm
        dip = (smoothstep(tm["bullet_in"][0], tm["bullet_in"][1], t)
               - smoothstep(tm["bullet_out"][0], tm["bullet_out"][1], t))
        return 1.0 - (1.0 - tm["bullet_rate"]) * dip

    def story_time(self, t):
        return integrate_rate(self.story_rate, t)

    # pulse kinematics: v(x) = v0 + a x^p, displacement normalised to arc length
    def _disp(self, x):
        tm = self.tm
        x = np.clip(x, 0.0, None)
        return tm["v0"] * x + tm["accel_a"] * x ** (tm["accel_p"] + 1.0) / (tm["accel_p"] + 1.0)

    def progress_from_story(self, tau):
        x = np.clip(np.asarray(tau, dtype=float) - self.tm["pulse_start"], 0.0, self._x_end)
        return self._disp(x) / self._disp_end

    def speed_from_story(self, tau):
        """Intrinsic pulse speed ds/dtau in scene units per story-second."""
        tm = self.tm
        x = np.asarray(tau, dtype=float) - tm["pulse_start"]
        inside = (x >= 0.0) & (x <= self._x_end)
        v = tm["v0"] + tm["accel_a"] * np.clip(x, 0.0, None) ** tm["accel_p"]
        return np.where(inside, v / self._disp_end * self.path.length, 0.0)

    def progress(self, t):
        return float(self.progress_from_story(self.story_time(t)))

    def pulse_s(self, t):
        return self.progress(t) * self.path.length

    def pulse_position(self, t):
        return self.path.point(self.pulse_s(t))

    # tables for every frame, evaluated from cumulative integrals on the same grid
    def grid_tables(self, t_max=None):
        t_max = self.duration if t_max is None else t_max
        x = cumulative_grid(t_max)
        story = cumulative_trapezoid(self.story_rate(x), x)
        world = cumulative_trapezoid(self.world_rate(x), x)
        prog = self.progress_from_story(story)
        return {
            "t": x,
            "story_time": story,
            "world_time": world,
            "world_rate": self.world_rate(x),
            "progress": prog,
            "s": prog * self.path.length,
            "pos": self.path.point(prog * self.path.length),
            "speed": self.speed_from_story(story),
        }

    def frame_tables(self):
        g = self.grid_tables()
        t = self.frame_to_time(self.frames)
        idx = np.rint(t * INTEGRATION_STEPS_PER_SECOND).astype(int)
        out = {k: v[idx] for k, v in g.items()}
        out["frame"] = self.frames
        return out

    def awaken(self, t):
        """Pulse brightness envelope 0..1 with a heartbeat flicker while it awakens."""
        tm = self.tm
        base = smootherstep(tm["awaken_start"], tm["pulse_start"], t)
        beat = 0.5 + 0.5 * np.cos(2 * math.pi * 1.25 * (np.asarray(t, dtype=float) - tm["awaken_start"]))
        flicker = 1.0 - 0.35 * beat * (1.0 - smoothstep(tm["pulse_start"] - 0.6, tm["pulse_start"] + 0.4, t))
        return base * flicker


# ---------------------------------------------------------- gear rotation ---

def gear_train_angles(timeline, centers, omegas, k_slow, t_frames):
    """Integrated driver angle per train: omega * integral g(t) (1 - k D(c, t)) dt.

    Evaluated by cumulative trapezoid on the fixed integration grid; each frame value
    equals integrate_rate(...) of that frame (see test_animation_math).
    """
    g = timeline.grid_tables(float(np.max(t_frames)) + 1e-9)
    centers = np.asarray(centers, dtype=float)
    d = distortion(centers[:, None, :], g["pos"][None, :, :], timeline.sigma)
    rate = g["world_rate"][None, :] * (1.0 - k_slow * d)
    cum = cumulative_trapezoid(rate, g["t"], axis=1)
    idx = np.rint(np.asarray(t_frames) * INTEGRATION_STEPS_PER_SECOND).astype(int)
    return np.asarray(omegas, dtype=float)[:, None] * cum[:, idx]


def gear_train_angle_single(timeline, center, omega, k_slow, t):
    def rate(x):
        st = cumulative_trapezoid(timeline.story_rate(x), x)
        pos = timeline.path.point(timeline.progress_from_story(st) * timeline.path.length)
        return timeline.world_rate(x) * (1.0 - k_slow * distortion(center, pos, timeline.sigma))
    return omega * integrate_rate(rate, t)


def tick_angle(t, t0, step_deg):
    """Mechanical second-hand tick: fast snap with a damped overshoot."""
    x = np.clip(np.asarray(t, dtype=float) - t0, 0.0, None)
    snap = 1.0 - np.exp(-18.0 * x) * np.cos(26.0 * x)
    return -math.radians(step_deg) * np.where(np.asarray(t) >= t0, snap, 0.0)


# ---------------------------------------------------------- fragment model ---

def fragment_offset(direction, trigger, gain, k, ampv, omega, phase, world_t):
    """x_i(t) = x_i0 + d_i s(t) + A_i (sin(w_i T + phi_i) - sin(phi_i)) gated by the fracture.

    s(t) = 1 - exp(-k * max(T_w - trigger, 0) * gain) is the bounded envelope; gain
    rescales each event's clock to its world-rate at fracture so every burst starts
    readable and then decelerates as world time keeps slowing.
    """
    tau = np.maximum(np.asarray(world_t) - trigger, 0.0) * gain
    env = 1.0 - np.exp(-k * tau)
    drift = np.sin(omega * world_t + phase) - np.sin(omega * trigger + phase)
    drift = np.where(np.asarray(world_t) >= trigger, drift, 0.0)
    return direction * env[..., None] + ampv * drift[..., None]


# ------------------------------------------------------------- camera rig ---

CAMERA_TRACKS = {
    # time (s) -> value. Azimuth is measured in the horizontal plane from the radial
    # (direction of travel) axis: 180 = behind the pulse, 90 = beside, 0 = ahead.
    "az": [(0.0, 112.0), (4.0, 140.0), (7.0, 158.0), (9.0, 163.0), (12.0, 150.0),
           (15.0, 158.0), (16.2, 164.0), (17.2, 85.0), (18.15, -24.0), (24.0, -30.0)],
    "dist": [(0.0, 17.0), (3.8, 8.0), (6.0, 6.6), (9.0, 6.4), (12.0, 5.2), (15.0, 5.4),
             (16.2, 6.0), (17.2, 5.0), (18.15, 5.6), (24.0, 5.6)],
    "el": [(0.0, 3.0), (4.0, 9.0), (7.0, 14.0), (10.0, 11.0), (13.0, 7.0), (16.2, 12.0),
           (17.2, 22.0), (18.15, 7.0), (24.0, 7.0)],
    "lens": [(0.0, 18.0), (4.0, 21.0), (8.0, 24.0), (12.0, 27.0), (15.5, 24.0),
             (17.2, 20.0), (19.0, 20.0), (24.0, 20.0)],
    "fstop": [(0.0, 4.5), (3.5, 3.2), (6.0, 2.8), (12.0, 2.6), (15.5, 3.5), (24.0, 3.5)],
}


class CameraRig:
    def __init__(self, timeline):
        self.tl = timeline
        tm = timeline.tm
        self.t_decouple = tm["bullet_out"][0] + 0.15
        self.reveal = tm["reveal_start"], tm["reveal_end"]
        self.top_height = 420.0
        self.top_lens = 32.0
        self.tip = timeline.path.point(timeline.path.length)

    def _track(self, name, t):
        k = CAMERA_TRACKS[name]
        return pchip([a for a, _ in k], [b for _, b in k], t)

    def state(self, t, pulse_pos=None, pulse_s=None):
        tl = self.tl
        if pulse_s is None:
            pulse_s = tl.pulse_s(t)
        if pulse_pos is None:
            pulse_pos = tl.path.point(pulse_s)
        # anchor follows the pulse, then lets it escape after the bullet-time beat
        if t <= self.t_decouple:
            anchor = pulse_pos
        else:
            s_dec = tl.pulse_s(self.t_decouple)
            anchor = tl.path.point(s_dec + 1.6 * (t - self.t_decouple))
        az = math.radians(float(self._track("az", t)))
        el = math.radians(float(self._track("el", t)))
        dist = float(self._track("dist", t))
        c = tl.clock
        offset = dist * (math.cos(el) * math.cos(az) * c.radial
                         + math.cos(el) * math.sin(az) * c.side
                         + math.sin(el) * c.up)
        pos_flight = anchor + offset

        look_pulse = pulse_pos + 0.8 * tl.path.tangent(pulse_s)
        w_fwd = float(smootherstep(self.t_decouple, self.t_decouple + 0.55, t))
        target_flight = (1 - w_fwd) * look_pulse + w_fwd * self.tip

        r0, r1 = self.reveal
        w_pos = float(smootherstep(r0, r1, t))
        w_xy = w_pos ** 1.6
        top = np.array([0.0, 0.0, self.top_height])
        pos = np.array([
            (1 - w_xy) * pos_flight[0] + w_xy * top[0],
            (1 - w_xy) * pos_flight[1] + w_xy * top[1],
            (1 - w_pos) * pos_flight[2] + w_pos * top[2],
        ])
        w_tgt = float(smootherstep(r0 + 0.3, r1 - 0.2, t))
        target = (1 - w_tgt) * target_flight + w_tgt * np.zeros(3)
        w_up = float(smootherstep(r0 + 1.0, r1 - 0.1, t))
        up = (1 - w_up) * np.array([0.0, 0.0, 1.0]) + w_up * np.array([0.0, 1.0, 0.0])
        up /= np.linalg.norm(up)
        lens = (1 - w_pos) * float(self._track("lens", t)) + w_pos * self.top_lens
        fstop = (1 - w_pos) * float(self._track("fstop", t)) + w_pos * 32.0
        focus_target = (1 - w_tgt) * pulse_pos + w_tgt * np.zeros(3)
        focus = float(np.linalg.norm(focus_target - pos))
        return {"pos": pos, "target": target, "up": up, "lens": lens,
                "fstop": fstop, "focus": max(focus, 0.1)}


def look_at_matrix(pos, target, up):
    """Rotation matrix (columns = camera local X, Y, Z) for a camera looking down -Z."""
    fwd = np.asarray(target, dtype=float) - np.asarray(pos, dtype=float)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    n = np.linalg.norm(right)
    if n < 1e-6:  # degenerate: pick any perpendicular
        right = np.cross(fwd, [1.0, 0.0, 0.0])
        n = np.linalg.norm(right)
    right /= n
    cam_up = np.cross(right, fwd)
    return np.stack([right, cam_up, -fwd], axis=1)
