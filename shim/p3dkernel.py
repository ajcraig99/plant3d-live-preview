"""
p3dkernel - the geometry engine behind the Plant 3D preview shim.

This module reimplements the *observable behaviour* of Plant 3D's embedded
Python geometry API on top of the `manifold3d` mesh-CSG kernel, so that the
exact same, unmodified custom-script `.py` files that ship to Plant 3D can be
executed and rendered on Linux.

Fidelity policy
---------------
The goal is NOT to be a "correct" CAD API. The goal is to reproduce what Plant
3D actually does, quirks and all, so that what you see in the preview is what
you get in Plant. Plant's API is famous for confusing / backwards naming
(notably `subtractFrom`). The semantics implemented here match the behaviour
the working repo scripts are written against:

    main.uniteWith(x)      ->  main = main  U  x     (result kept in caller)
    main.subtractFrom(x)   ->  main = main  -  x     (result kept in caller)
    main.intersectWith(x)  ->  main = main  n  x     (result kept in caller)

If a Plant quirk ever needs to be mirrored more precisely, this file is the one
and only place to change it.

Orientation conventions (verified against the repo scripts):
    BOX(L,W,H)         centred on the origin; H->X, L->Y, W->Z
    CYLINDER(R,H,O)    base on the Z=0 plane, axis +Z; O = hole radius (hollow)
    CONE(R1,R2,H,E)    base radius R1 on Z=0, top radius R2 at Z=H, axis +Z
    TORUS(R1,R2)       centred on origin, ring in XY plane about Z; R2 = tube r
    SPHERE(R)          centred on origin
    rotateX/Y/Z(deg)   degrees, about the world origin, mutates in place
    translate((x,y,z)) mutates in place; chaining is left-to-right
"""

from manifold3d import Manifold, CrossSection

# Facet count for round primitives. Higher = smoother preview but slower
# booleans. This is a preview, so favour looks; override via P3D_SEGMENTS env.
import os
import math
SEGMENTS = int(os.environ.get("P3D_SEGMENTS", "96"))

# Tiny overlap used to avoid coplanar faces on through-cuts (cosmetic only).
_EPS = 1e-4


def _rot(p, axis, deg):
    """Rotate point p about world axis (0=X, 1=Y, 2=Z) by `deg` degrees,
    right-handed, matching Manifold.rotate."""
    a = math.radians(deg)
    c, sn = math.cos(a), math.sin(a)
    x, y, z = p
    if axis == 0:
        return (x, y * c - z * sn, y * sn + z * c)
    if axis == 1:
        return (x * c + z * sn, y, -x * sn + z * c)
    return (x * c - y * sn, x * sn + y * c, z)


class Scene:
    """The `s` object passed as the first argument to every primitive and to
    the script's entry function. Owns every solid created during a run and
    collects the ports / dimensions the script declares."""

    def __init__(self, segments=None):
        self.segments = int(segments) if segments else SEGMENTS
        self.solids = []        # every Solid ever created, in creation order
        self.points = []        # {'pos':(x,y,z), 'dir':(dx,dy,dz), 'extra':(...)}
        self.dims = []          # {'name':str, 'a':(x,y,z), 'b':(x,y,z)}
        self.warnings = []      # stubbed / unknown API calls, surfaced to user

    # -- registration --------------------------------------------------------
    def _register(self, solid):
        self.solids.append(solid)

    def live_solids(self):
        return [
            s for s in self.solids
            if not s.erased and not s.consumed and not s.m.is_empty()
        ]

    def primitive_dims(self):
        """Defining lengths of every live primitive, in world coordinates,
        as [{'primitive','name','a','b'}]. Feeds the viewer's Fixed dims."""
        return [
            {"primitive": s.primitive, "name": d["name"], "a": d["a"], "b": d["b"]}
            for s in self.live_solids() for d in s.dims
        ]

    # -- ports & dimensions --------------------------------------------------
    def setPoint(self, pos, direction, *extra):
        self.points.append({
            "pos": tuple(float(x) for x in pos),
            "dir": tuple(float(x) for x in direction),
            "extra": extra,
        })

    def setLinearDimension(self, name, a, b, *extra):
        self.dims.append({
            "name": str(name),
            "a": tuple(float(x) for x in a),
            "b": tuple(float(x) for x in b),
        })

    # -- tolerance for the odd extra s.* method a script might call ----------
    def __getattr__(self, name):
        # Only reached when a real attribute/method is missing. Return a no-op
        # so a stray Plant-ism doesn't abort the whole preview, but record it.
        def _stub(*a, **k):
            msg = "s.%s(...) is not implemented in the preview shim (ignored)" % name
            if msg not in self.warnings:
                self.warnings.append(msg)
            return None
        return _stub


class Solid:
    """Wraps a manifold3d.Manifold and exposes the Plant 3D transform / boolean
    method surface. Transforms and booleans mutate in place and return self so
    they can be chained, exactly like the Plant API.

    `dims` holds the primitive's defining lengths as world-space segments and
    is kept in step with every transform, so the viewer can label them."""

    __slots__ = ("scene", "m", "erased", "consumed", "primitive", "dims")

    def __init__(self, scene, manifold, primitive="SOLID", dims=None):
        self.scene = scene
        self.m = manifold
        self.erased = False
        self.consumed = False
        self.primitive = primitive
        self.dims = list(dims or [])
        scene._register(self)

    def _map_dims(self, f):
        self.dims = [{"name": d["name"], "a": f(d["a"]), "b": f(d["b"])} for d in self.dims]

    # -- transforms (mutate in place, chainable) -----------------------------
    def translate(self, v):
        t = (float(v[0]), float(v[1]), float(v[2]))
        self.m = self.m.translate(t)
        self._map_dims(lambda p: (p[0] + t[0], p[1] + t[1], p[2] + t[2]))
        return self

    def rotateX(self, deg):
        self.m = self.m.rotate((float(deg), 0.0, 0.0))
        self._map_dims(lambda p: _rot(p, 0, float(deg)))
        return self

    def rotateY(self, deg):
        self.m = self.m.rotate((0.0, float(deg), 0.0))
        self._map_dims(lambda p: _rot(p, 1, float(deg)))
        return self

    def rotateZ(self, deg):
        self.m = self.m.rotate((0.0, 0.0, float(deg)))
        self._map_dims(lambda p: _rot(p, 2, float(deg)))
        return self

    def scale(self, v):
        if isinstance(v, (int, float)):
            v = (v, v, v)
        sx, sy, sz = float(v[0]), float(v[1]), float(v[2])
        self.m = self.m.scale((sx, sy, sz))
        self._map_dims(lambda p: (p[0] * sx, p[1] * sy, p[2] * sz))
        return self

    # -- booleans (caller keeps the result; see fidelity policy above) --------
    def uniteWith(self, other):
        self.m = self.m + other.m
        other.consumed = True
        return self

    def subtractFrom(self, other):
        # Plant: main.subtractFrom(cutter)  ==  main = main - cutter
        self.m = self.m - other.m
        other.consumed = True
        return self

    def intersectWith(self, other):
        self.m = self.m ^ other.m
        other.consumed = True
        return self

    # -- lifecycle -----------------------------------------------------------
    def erase(self):
        self.erased = True
        return self

    # -- query methods (rarely used by repo scripts, kept for tolerance) -----
    def parameters(self):
        return {}

    def numberOfPoints(self):
        return 0

    def transformationMatrix(self):
        return None


# ---------------------------------------------------------------------------
# Primitive constructors. Each takes the scene `s` first and returns a Solid.
# ---------------------------------------------------------------------------

def _seg(name, a, b):
    return {"name": name, "a": tuple(float(x) for x in a), "b": tuple(float(x) for x in b)}


def _finish(s, name, manifold, args, dims=()):
    """Wrap `manifold` in a Solid and warn if it came out empty, which is what
    happens for zero or negative sizes. A silently missing part is confusing
    in a preview, so say so."""
    solid = Solid(s, manifold, primitive=name, dims=dims)
    if manifold.is_empty():
        desc = ", ".join("%s=%s" % (k, v) for k, v in args.items())
        s.warnings.append(
            "%s(%s) produced no geometry (check for zero or negative sizes)" % (name, desc))
    return solid


def BOX(s, L=1.0, W=1.0, H=1.0, **kw):
    L, W, H = float(L), float(W), float(H)
    c = (-H / 2.0, -L / 2.0, -W / 2.0)          # min corner; H->X, L->Y, W->Z
    dims = [
        _seg("H", c, (c[0] + H, c[1], c[2])),
        _seg("L", c, (c[0], c[1] + L, c[2])),
        _seg("W", c, (c[0], c[1], c[2] + W)),
    ]
    return _finish(s, "BOX", Manifold.cube([H, L, W], True), {"L": L, "W": W, "H": H}, dims)


def CYLINDER(s, R=None, H=1.0, O=0.0, R1=None, R2=None, **kw):
    H = float(H)
    dims = [_seg("H", (0, 0, 0), (0, 0, H))]
    # Elliptical / tapered form CYLINDER(R1=, R2=, H=, O=) -> treat as cone-ish.
    if R is None and R1 is not None:
        low = float(R1)
        high = float(R2) if R2 is not None else float(R1)
        outer = Manifold.cylinder(H, low, high, s.segments, False)
        dims.append(_seg("R1", (0, 0, 0), (low, 0, 0)))
        dims.append(_seg("R2", (0, 0, H), (high, 0, H)))
    else:
        r = float(R if R is not None else (R1 if R1 is not None else 1.0))
        outer = Manifold.cylinder(H, r, r, s.segments, False)
        dims.append(_seg("R", (0, 0, 0), (r, 0, 0)))
    O = float(O or 0.0)
    if O > 0.0:
        bore = Manifold.cylinder(H + 2 * _EPS, O, O, s.segments, False).translate((0, 0, -_EPS))
        outer = outer - bore
        dims.append(_seg("O", (0, 0, H), (O, 0, H)))
    return _finish(s, "CYLINDER", outer, {"R": R, "H": H, "O": O, "R1": R1, "R2": R2}, dims)


def CONE(s, R1=1.0, R2=0.0, H=1.0, E=0.0, **kw):
    # E (eccentricity) is 0.0 everywhere in the repo; concentric cone.
    R1, R2, H = float(R1), float(R2), float(H)
    dims = [_seg("H", (0, 0, 0), (0, 0, H)), _seg("R1", (0, 0, 0), (R1, 0, 0))]
    if R2 > 0.0:
        dims.append(_seg("R2", (0, 0, H), (R2, 0, H)))
    return _finish(s, "CONE", Manifold.cylinder(H, R1, R2, s.segments, False),
                   {"R1": R1, "R2": R2, "H": H}, dims)


def TORUS(s, R1=1.0, R2=0.5, **kw):
    # Ring radius R1, tube radius R2. Revolve a circle; manifold's revolve puts
    # the resulting axis on Z, matching Plant's TORUS (ring in XY plane).
    R1, R2 = float(R1), float(R2)
    circle = CrossSection.circle(R2, s.segments).translate((R1, 0.0))
    dims = [_seg("R1", (0, 0, 0), (R1, 0, 0)), _seg("R2", (R1, 0, 0), (R1 + R2, 0, 0))]
    return _finish(s, "TORUS", Manifold.revolve(circle, s.segments, 360.0), {"R1": R1, "R2": R2}, dims)


def SPHERE(s, R=1.0, **kw):
    R = float(R)
    return _finish(s, "SPHERE", Manifold.sphere(R, s.segments), {"R": R},
                   [_seg("R", (0, 0, 0), (R, 0, 0))])


def HALFSPHERE(s, R=1.0, **kw):
    R = float(R)
    sph = Manifold.sphere(R, s.segments)
    # keep the +Z half
    box = Manifold.cube([4 * R, 4 * R, 4 * R], True).translate((0, 0, 2 * R))
    return _finish(s, "HALFSPHERE", sph ^ box, {"R": R}, [_seg("R", (0, 0, 0), (0, 0, R))])


def ELLIPSOIDHEAD(s, R=1.0, H=None, **kw):
    # Approximate a 2:1 ellipsoidal head as a squashed half-sphere.
    r = float(R)
    h = float(H) if H is not None else r / 2.0
    sph = Manifold.sphere(r, s.segments)
    box = Manifold.cube([4 * r, 4 * r, 4 * r], True).translate((0, 0, 2 * r))
    dims = [_seg("R", (0, 0, 0), (r, 0, 0)), _seg("H", (0, 0, 0), (0, 0, h))]
    return _finish(s, "ELLIPSOIDHEAD", (sph ^ box).scale((1.0, 1.0, h / r)), {"R": R, "H": h}, dims)
