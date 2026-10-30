"""Deterministic procedural geometry for CHRONOBREAK (pure NumPy, no bpy).

* gear_mesh        - toothed wheel (rim, hub, spokes) as verts/faces
* layout_gears     - seeded placement of meshing gear trains avoiding the pulse path,
                     the camera path and the camera->pulse sight line
* fracture_events  - which gears the passing pulse shatters, and when
* gear_fragments / field_fragments - per-shard attributes for the Geometry Nodes system
* shard_points     - point clouds whose convex hulls become the shard archetypes
"""
import math

import numpy as np

import animation_math as am

GEAR_ARCHETYPES = [
    {"teeth": 12, "spokes": 0},
    {"teeth": 18, "spokes": 0},
    {"teeth": 24, "spokes": 4},
    {"teeth": 32, "spokes": 5},
    {"teeth": 40, "spokes": 5},
    {"teeth": 48, "spokes": 6},
    {"teeth": 60, "spokes": 6},
    {"teeth": 72, "spokes": 8},
    {"teeth": 96, "spokes": 8},
    {"teeth": 120, "spokes": 10},
]
GEAR_THICKNESS = 1.1  # in module units


def gear_dims(teeth):
    rp = teeth / 2.0
    ra = rp + 1.0
    rf = rp - 1.25
    rim_in = rf - max(1.1, 0.07 * rp)
    hub = max(1.7, 0.16 * rp)
    return {"pitch": rp, "tip": ra, "root": rf, "rim_in": rim_in, "hub": hub, "bore": 0.55}


# ------------------------------------------------------------ mesh helpers ---

def _ring_prism(outer, inner, z0, z1):
    """Prism between two closed XY loops with equal vertex counts (CCW)."""
    n = len(outer)
    verts = []
    for z in (z0, z1):
        verts += [(x, y, z) for x, y in outer]
        verts += [(x, y, z) for x, y in inner]
    ob, ib, ot, it = 0, n, 2 * n, 3 * n
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((ot + i, ot + j, it + j, it + i))   # top
        faces.append((ob + j, ob + i, ib + i, ib + j))   # bottom
        faces.append((ob + i, ob + j, ot + j, ot + i))   # outer wall
        faces.append((ib + j, ib + i, it + i, it + j))   # inner wall
    return verts, faces


def _box(cx, cy, angle, length, width, z0, z1):
    c, s = math.cos(angle), math.sin(angle)
    hl, hw = length / 2, width / 2
    corners = [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]
    pts = [(cx + x * c - y * s, cy + x * s + y * c) for x, y in corners]
    verts = [(x, y, z0) for x, y in pts] + [(x, y, z1) for x, y in pts]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return verts, faces


def _circle(r, n, phase=0.0):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False) + phase
    return list(zip(r * np.cos(a), r * np.sin(a)))


def merge(parts):
    verts, faces = [], []
    for v, f in parts:
        off = len(verts)
        verts += list(v)
        faces += [tuple(i + off for i in face) for face in f]
    return verts, faces


def gear_mesh(teeth, spokes):
    """Gear of module 1 centred at the origin, tooth 0 centred on +X, thickness along Z."""
    d = gear_dims(teeth)
    p = 2 * math.pi / teeth
    profile = [(-0.31, d["root"]), (-0.25, d["pitch"]), (-0.16, d["tip"]),
               (0.16, d["tip"]), (0.25, d["pitch"]), (0.31, d["root"]), (0.5, d["root"])]
    outer, angles = [], []
    for k in range(teeth):
        for frac, r in profile:
            a = (k + frac) * p
            outer.append((r * math.cos(a), r * math.sin(a)))
            angles.append(a)
    # rotate list so the loop starts at the first root point (angles increase CCW)
    order = np.argsort(np.mod(angles, 2 * math.pi))
    outer = [outer[i] for i in order]
    angles = np.mod(np.asarray(angles)[order], 2 * math.pi)
    h = GEAR_THICKNESS / 2
    inner_r = d["rim_in"] if spokes else d["bore"] + 0.25
    inner = [(inner_r * math.cos(a), inner_r * math.sin(a)) for a in angles]
    parts = [_ring_prism(outer, inner, -h, h)]
    if spokes:
        nh = 48
        parts.append(_ring_prism(_circle(d["hub"], nh), _circle(d["bore"], nh), -h * 1.45, h * 1.45))
        length = d["rim_in"] - d["hub"] + 0.4
        mid = (d["rim_in"] + d["hub"]) / 2
        width = max(0.75, 0.075 * d["pitch"])
        for i in range(spokes):
            a = 2 * math.pi * (i + 0.5) / spokes
            parts.append(_box(mid * math.cos(a), mid * math.sin(a), a, length, width, -h * 0.75, h * 0.75))
    return merge(parts)


def annulus_mesh(r_in, r_out, z0, z1, segments=192):
    return _ring_prism(_circle(r_out, segments), _circle(r_in, segments), z0, z1)


def shard_points(rng, n_points=14):
    """Random points in a flattened, elongated ellipsoid: a sliver of broken plate."""
    axes = np.array([1.0, rng.uniform(0.35, 0.75), rng.uniform(0.07, 0.18)])
    v = rng.normal(size=(n_points, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    v *= rng.uniform(0.55, 1.0, size=(n_points, 1)) ** 0.5
    return v * axes


# ----------------------------------------------------------------- layout ---

def _disc_hits(points, center, radius, half_h, margin):
    if len(points) == 0:
        return False
    dz = np.abs(points[:, 2] - center[2])
    dxy = np.hypot(points[:, 0] - center[0], points[:, 1] - center[1])
    return bool(np.any((dz < half_h + margin) & (dxy < radius + margin)))


def keepout_points(timeline, rig, step=2):
    """Pulse path, camera path and camera->pulse sight lines sampled over the flight."""
    path = timeline.path.point(np.linspace(0, timeline.path.length, 900))
    ft = timeline.frame_tables()
    t_end = timeline.tm["reveal_start"] + 0.4
    cams, los = [], []
    for i in range(0, len(ft["t"]), step):
        t = ft["t"][i]
        if t > t_end:
            break
        st = rig.state(t, ft["pos"][i], ft["s"][i])
        cams.append(st["pos"])
        a, b = st["pos"], ft["pos"][i]
        for w in np.linspace(0.08, 0.9, 10):
            los.append(a + (b - a) * w)
    return path, np.array(cams), np.array(los)


def layout_gears(cfg, timeline, keepout, rng):
    gcfg = cfg["gears"]
    clock = timeline.clock
    path_pts, cam_pts, los_pts = keepout
    r_max = cfg["clock"]["radius_inner_mechanism"]
    gears = []
    tail_dir = -clock.radial
    tail_pts = np.array([tail_dir * r + np.array([0, 0, 3.0]) for r in np.linspace(0, 24, 40)])

    def collides(c, radius, half_h, ignore=()):
        if math.hypot(c[0], c[1]) + radius > r_max:
            return True
        if math.hypot(c[0], c[1]) < radius + 3.6 and abs(c[2]) < 60:  # centre post
            return True
        if _disc_hits(path_pts, c, radius, half_h, 1.7):
            return True
        # nothing may hide the second hand (path + tail) from the final top-down camera
        for pts in (path_pts, tail_pts):
            dxy = np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1])
            if np.any((dxy < radius + 1.4) & (c[2] + half_h > pts[:, 2] - 0.4)):
                return True
        if _disc_hits(cam_pts, c, radius, half_h, 1.4):
            return True
        if _disc_hits(los_pts, c, radius, half_h, 0.35):
            return True
        for j, g in enumerate(gears):
            if j in ignore:
                continue
            if (abs(g["center"][2] - c[2]) < g["half_h"] + half_h + 0.35
                    and math.hypot(g["center"][0] - c[0], g["center"][1] - c[1]) < g["radius"] + radius + 0.35):
                return True
        return False

    train = 0
    attempts = 0
    while len(gears) < gcfg["target_count"] and attempts < gcfg["max_attempts"]:
        attempts += 1
        arch = int(rng.integers(0, len(GEAR_ARCHETYPES)))
        teeth = GEAR_ARCHETYPES[arch]["teeth"]
        module = float(rng.choice([0.32, 0.4, 0.5, 0.62, 0.75]))
        radius = (teeth / 2 + 1) * module
        half_h = GEAR_THICKNESS / 2 * module * 1.45
        if rng.random() < gcfg["near_path_fraction"]:
            s = rng.uniform(0.0, timeline.path.length)
            base = timeline.path.point(s)
            lateral = rng.choice([-1, 1]) * rng.uniform(radius * 0.4, radius + 14.0)
            dh = rng.uniform(-12.0, 12.0)
            c = base + lateral * clock.side + dh * clock.up + rng.uniform(-4, 4) * clock.radial
        else:
            r = math.sqrt(rng.uniform(0.02, 1.0)) * r_max
            a = rng.uniform(0, 2 * math.pi)
            c = np.array([r * math.sin(a), r * math.cos(a), float(rng.choice([-2.5, 4.0, 11.0, 18.0, 25.0]))])
        c[2] = float(np.clip(c[2], -2.5, 30.0))
        if collides(c, radius, half_h):
            continue
        omega = float(rng.uniform(0.9, 1.6) / max(radius, 1.0) ** 0.6 * rng.choice([-1, 1]))
        driver = {"center": c, "teeth": teeth, "arch": arch, "module": module, "radius": radius,
                  "half_h": half_h, "train": train, "ratio": 1.0, "phase": float(rng.uniform(0, 2 * math.pi)),
                  "omega": omega, "driver_center": c.copy()}
        gears.append(driver)
        idx_prev, prev = len(gears) - 1, driver
        for _ in range(int(rng.integers(0, 3))):
            arch2 = int(rng.integers(0, len(GEAR_ARCHETYPES)))
            t2 = GEAR_ARCHETYPES[arch2]["teeth"]
            r2 = (t2 / 2 + 1) * module
            alpha = rng.uniform(0, 2 * math.pi)
            dist = (prev["teeth"] + t2) / 2 * module
            c2 = prev["center"] + dist * np.array([math.cos(alpha), math.sin(alpha), 0.0])
            if collides(c2, r2, half_h, ignore=(idx_prev,)):
                continue
            # theta2 = alpha + pi - pi/N2 - (N1/N2)(theta1 - alpha), theta1 = phase1 + ratio1 * Theta
            k = prev["teeth"] / t2
            phase2 = alpha + math.pi - math.pi / t2 - k * (prev["phase"] - alpha)
            g2 = {"center": c2, "teeth": t2, "arch": arch2, "module": module, "radius": r2,
                  "half_h": half_h, "train": train, "ratio": -k * prev["ratio"], "phase": phase2,
                  "omega": omega, "driver_center": c.copy()}
            gears.append(g2)
            idx_prev, prev = len(gears) - 1, g2
        train += 1
    return gears


def fracture_events(cfg, timeline, gears):
    """Closest approach of the pulse to each gear inside the fracture window."""
    dcfg = cfg["distortion"]
    g = timeline.grid_tables()
    w0, w1 = dcfg["fracture_window"]
    sel = (g["t"] >= w0) & (g["t"] <= w1)
    t, pos = g["t"][sel], g["pos"][sel]
    for gear in gears:
        c = gear["center"]
        dxy = np.maximum(np.hypot(pos[:, 0] - c[0], pos[:, 1] - c[1]) - gear["radius"], 0.0)
        dz = np.maximum(np.abs(pos[:, 2] - c[2]) - gear["half_h"], 0.0)
        d = np.hypot(dxy, dz)
        i = int(np.argmin(d))
        gear["fracture_t"] = float(t[i]) if d[i] < dcfg["fracture_radius"] else None
        gear["closest_point"] = pos[i]
    return gears


def gear_fragments(cfg, timeline, gears, rng):
    """Sample shards on the material of every fractured gear."""
    fcfg = cfg["fragments"]
    rows = []
    for gear in gears:
        if gear.get("fracture_t") is None:
            continue
        d = gear_dims(gear["teeth"])
        m = gear["module"]
        area = math.pi * (d["tip"] ** 2 - d["rim_in"] ** 2) * m * m
        n = int(np.clip(area * fcfg["per_gear_density"], 30, fcfg["max_per_gear"]))
        r = np.sqrt(rng.uniform((d["rim_in"] * m) ** 2, (d["pitch"] * m) ** 2, n))
        a = rng.uniform(0, 2 * math.pi, n)
        c = gear["center"]
        local = np.stack([r * np.cos(a), r * np.sin(a), rng.uniform(-1, 1, n) * gear["half_h"] * 0.5], axis=1)
        origin = c + local
        t_f = gear["fracture_t"]
        s_f = timeline.pulse_s(t_f)
        tangent = timeline.path.tangent(s_f)
        hit = gear["closest_point"]
        away = origin - hit
        away /= np.linalg.norm(away, axis=1, keepdims=True) + 1e-9
        radial = local / (np.linalg.norm(local, axis=1, keepdims=True) + 1e-9)
        mag = rng.uniform(0.6, 1.4, (n, 1))
        direction = (radial * rng.uniform(0.8, 2.2, (n, 1)) * (1 + 0.1 * gear["radius"])
                     + away * rng.uniform(1.5, 4.0, (n, 1))
                     + tangent * rng.uniform(0.5, 4.5, (n, 1))
                     + rng.normal(0, 0.6, (n, 3))) * mag
        world_tf = timeline.world_time(t_f)
        gain = 0.55 / max(float(timeline.world_rate(t_f)), 1e-3)
        delay = np.linalg.norm(origin - hit, axis=1) / 45.0 / gain  # shock front, world seconds
        rows.append({
            "origin": origin,
            "dir": direction,
            "trigger": world_tf + delay,
            "gain": np.full(n, gain),
            "amp": rng.normal(0, 0.25, (n, 3)),
            "omega": rng.uniform(0.8, 2.0, n),
            "phase": rng.uniform(0, 2 * math.pi, n),
            "scale": m * rng.uniform(0.3, 0.85, n),
            "rot0": rng.uniform(0, 2 * math.pi, (n, 3)),
            "axis": _unit(rng.normal(size=(n, 3))),
            "spin": rng.uniform(1.0, 5.0, n),
            "tint": np.full(n, gear.get("tint", 0.0)),
            "variant": rng.integers(0, 8, n),
        })
    return rows


def field_fragments(cfg, timeline, keepout, gears, rng):
    """The suspended field the pulse crosses in shot D: already shattered, nearly still."""
    fcfg = cfg["fragments"]
    _, cam_pts, _ = keepout
    n_target = fcfg["field_count"]
    p0, p1 = fcfg["field_progress"]
    rmin, rmax = fcfg["field_radius"]
    clock = timeline.clock
    out = []
    while sum(len(o) for o in out) < n_target:
        n = 4000
        s = rng.uniform(p0, p1, n) * timeline.path.length
        base = timeline.path.point(s)
        tan = timeline.path.tangent(s)
        ortho_a = np.tile(clock.side, (n, 1))
        ortho_b = np.cross(tan, ortho_a)
        rho = rmin + (rmax - rmin) * rng.uniform(0, 1, n) ** 1.5
        phi = rng.uniform(0, 2 * math.pi, n)
        pts = base + rho[:, None] * (np.cos(phi)[:, None] * ortho_a + np.sin(phi)[:, None] * ortho_b)
        ok = (pts[:, 2] > -1.0) & (pts[:, 2] < 34.0) & (np.hypot(pts[:, 0], pts[:, 1]) < 121.0)
        d_cam = np.min(np.linalg.norm(pts[:, None, :] - cam_pts[None, ::2, :], axis=2), axis=1)
        ok &= d_cam > 2.4
        for gear in gears:
            if gear.get("fracture_t") is not None:
                continue
            c = gear["center"]
            ok &= ~((np.abs(pts[:, 2] - c[2]) < gear["half_h"] + 0.6)
                    & (np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1]) < gear["radius"] + 0.6))
        out.append(pts[ok])
    pts = np.concatenate(out)[:n_target]
    n = len(pts)
    return [{
        "origin": pts,
        "dir": rng.normal(0, 0.15, (n, 3)),
        "trigger": np.full(n, -1000.0),
        "gain": np.ones(n),
        "amp": rng.normal(0, 0.35, (n, 3)),
        "omega": rng.uniform(0.6, 1.6, n),
        "phase": rng.uniform(0, 2 * math.pi, n),
        "scale": rng.uniform(0.07, 0.38, n) * (1 + 0.8 * (rng.uniform(0, 1, n) < 0.06)),
        "rot0": rng.uniform(0, 2 * math.pi, (n, 3)),
        "axis": _unit(rng.normal(size=(n, 3))),
        "spin": rng.uniform(0.2, 1.2, n),
        "tint": (rng.uniform(0, 1, n) < 0.3).astype(float),
        "variant": rng.integers(0, 8, n),
    }]


def concat_fragments(rows):
    keys = rows[0].keys()
    return {k: np.concatenate([r[k] for r in rows]) for k in keys}


def cull_near_camera(frags, cam_pts, clearance=3.0):
    """Drop shards whose rest or fully-burst position comes within `clearance` of the lens."""
    keep = np.ones(len(frags["origin"]), bool)
    for pts in (frags["origin"], frags["origin"] + frags["dir"]):
        for i in range(0, len(pts), 2000):
            d = np.min(np.linalg.norm(pts[i:i + 2000, None, :] - cam_pts[None, :, :], axis=2), axis=1)
            keep[i:i + 2000] &= d > clearance
    return {k: v[keep] for k, v in frags.items()}


def _unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def build_layout(cfg):
    """Full deterministic layout from config (used by Blender build and by tests)."""
    tl = am.Timeline(cfg)
    rig = am.CameraRig(tl)
    rng = np.random.default_rng(cfg["seed"])
    keep = keepout_points(tl, rig)
    gears = layout_gears(cfg, tl, keep, rng)
    for g in gears:
        g["tint"] = float(rng.choice([0.0, 0.0, 1.0, 2.0], p=[0.35, 0.2, 0.3, 0.15]))
    fracture_events(cfg, tl, gears)
    frag_rng = np.random.default_rng(cfg["seed"] + 1)
    rows = gear_fragments(cfg, tl, gears, frag_rng) + field_fragments(cfg, tl, keep, gears, frag_rng)
    return tl, rig, gears, cull_near_camera(concat_fragments(rows), keepout_points(tl, rig, step=1)[1])
