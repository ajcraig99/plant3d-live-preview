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
SEGMENTS = int(os.environ.get("P3D_SEGMENTS", "96"))

# Tiny overlap used to avoid coplanar faces on through-cuts (cosmetic only).
_EPS = 1e-4


class Scene:
    """The `s` object passed as the first argument to every primitive and to
    the script's entry function. Owns every solid created during a run and
    collects the ports / dimensions the script declares."""

    def __init__(self):
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
    they can be chained, exactly like the Plant API."""

    __slots__ = ("scene", "m", "erased", "consumed")

    def __init__(self, scene, manifold):
        self.scene = scene
        self.m = manifold
        self.erased = False
        self.consumed = False
        scene._register(self)

    # -- transforms (mutate in place, chainable) -----------------------------
    def translate(self, v):
        self.m = self.m.translate((float(v[0]), float(v[1]), float(v[2])))
        return self

    def rotateX(self, deg):
        self.m = self.m.rotate((float(deg), 0.0, 0.0))
        return self

    def rotateY(self, deg):
        self.m = self.m.rotate((0.0, float(deg), 0.0))
        return self

    def rotateZ(self, deg):
        self.m = self.m.rotate((0.0, 0.0, float(deg)))
        return self

    def scale(self, v):
        if isinstance(v, (int, float)):
            v = (v, v, v)
        self.m = self.m.scale((float(v[0]), float(v[1]), float(v[2])))
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

def BOX(s, L=1.0, W=1.0, H=1.0, **kw):
    return Solid(s, Manifold.cube([float(H), float(L), float(W)], True))


def CYLINDER(s, R=None, H=1.0, O=0.0, R1=None, R2=None, **kw):
    H = float(H)
    # Elliptical / tapered form CYLINDER(R1=, R2=, H=, O=) -> treat as cone-ish.
    if R is None and R1 is not None:
        low = float(R1)
        high = float(R2) if R2 is not None else float(R1)
        outer = Manifold.cylinder(H, low, high, SEGMENTS, False)
    else:
        r = float(R if R is not None else (R1 if R1 is not None else 1.0))
        outer = Manifold.cylinder(H, r, r, SEGMENTS, False)
    solid = Solid(s, outer)
    O = float(O or 0.0)
    if O > 0.0:
        bore = Manifold.cylinder(H + 2 * _EPS, O, O, SEGMENTS, False).translate((0, 0, -_EPS))
        solid.m = solid.m - bore
    return solid


def CONE(s, R1=1.0, R2=0.0, H=1.0, E=0.0, **kw):
    # E (eccentricity) is 0.0 everywhere in the repo; concentric cone.
    return Solid(s, Manifold.cylinder(float(H), float(R1), float(R2), SEGMENTS, False))


def TORUS(s, R1=1.0, R2=0.5, **kw):
    # Ring radius R1, tube radius R2. Revolve a circle; manifold's revolve puts
    # the resulting axis on Z, matching Plant's TORUS (ring in XY plane).
    circle = CrossSection.circle(float(R2), SEGMENTS).translate((float(R1), 0.0))
    return Solid(s, Manifold.revolve(circle, SEGMENTS, 360.0))


def SPHERE(s, R=1.0, **kw):
    return Solid(s, Manifold.sphere(float(R), SEGMENTS))


def HALFSPHERE(s, R=1.0, **kw):
    sph = Manifold.sphere(float(R), SEGMENTS)
    # keep the +Z half
    box = Manifold.cube([4 * float(R), 4 * float(R), 4 * float(R)], True).translate((0, 0, 2 * float(R)))
    return Solid(s, sph ^ box)


def ELLIPSOIDHEAD(s, R=1.0, H=None, **kw):
    # Approximate a 2:1 ellipsoidal head as a squashed half-sphere.
    r = float(R)
    h = float(H) if H is not None else r / 2.0
    sph = Manifold.sphere(r, SEGMENTS)
    box = Manifold.cube([4 * r, 4 * r, 4 * r], True).translate((0, 0, 2 * r))
    return Solid(s, (sph ^ box).scale((1.0, 1.0, h / r)))
