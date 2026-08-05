"""
Shim for `from varmain.primitiv import *`.

Exposes the primitive constructors the repo scripts use. Any primitive that a
script references but that isn't implemented here resolves through the module
`__getattr__` fallback below, which returns a small placeholder box and records
a warning instead of crashing the whole preview.
"""

from p3dkernel import (
    Solid,
    BOX,
    CYLINDER,
    CONE,
    TORUS,
    SPHERE,
    HALFSPHERE,
    ELLIPSOIDHEAD,
)
from manifold3d import Manifold

# Known Plant primitive names that we don't model precisely yet. Referencing
# any of these produces a labelled placeholder so geometry authors can see
# "something is here" and where, rather than getting an AttributeError.
_UNMODELLED = {
    "ARC3D", "ARC3D2", "ARC3DS", "PYRAMID", "ROUNDRECT", "SPHERESEGMENT",
    "ELLIPSOIDHEAD2", "ELLIPSOIDSEGMENT", "TORISPHERICHEAD", "TORISPHERICHEAD2",
    "TORISPHERICHEADH", "CORNERBOX", "EQBOX", "EQCONE", "EQCYLINDER",
    "EQHALFSPHERE", "CDBOX", "CDCYLINDER",
}


def __getattr__(name):
    if name in _UNMODELLED or name.isupper():
        def _placeholder(s, **kw):
            msg = ("primitive %s() is not modelled in the preview shim; "
                   "drawing a placeholder cube" % name)
            if msg not in s.warnings:
                s.warnings.append(msg)
            # size the placeholder from any radius/length-ish kwargs given
            hint = 10.0
            for k in ("R", "R1", "D", "L", "H", "W"):
                if k in kw:
                    try:
                        hint = max(hint, float(kw[k]))
                    except (TypeError, ValueError):
                        pass
            return Solid(s, Manifold.cube([hint, hint, hint], True))
        return _placeholder
    raise AttributeError("module 'varmain.primitiv' has no attribute %r" % name)
