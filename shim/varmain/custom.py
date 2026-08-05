"""
Shim for `from varmain.custom import *`.

Provides the metadata decorators (@activate, @group, @param, @enum) and the
parameter-type constants (LENGTH, LENGTH0, ANGLE, ENUM, ...). The decorators
have no effect on geometry; they simply record metadata onto the entry function
as `._p3d_meta` so the preview UI can build a parameter panel with the right
labels, tooltips and defaults.
"""


class ParamType:
    def __init__(self, name, allow_negative=False, allow_zero=True):
        self.name = name
        self.allow_negative = allow_negative
        self.allow_zero = allow_zero

    def __repr__(self):
        return "<ParamType %s>" % self.name


# Types documented in the master reference.
LENGTH = ParamType("LENGTH", allow_negative=False, allow_zero=False)
LENGTH0 = ParamType("LENGTH0", allow_negative=False, allow_zero=True)
ANGLE = ParamType("ANGLE", allow_negative=True)
ENUM = ParamType("ENUM")
INT = ParamType("INT", allow_negative=True)
INTEGER = INT
BOOL = ParamType("BOOL")
BOOLEAN = BOOL
STRING = ParamType("STRING")
# Lowercase aliases used in some Plant docs.
d = LENGTH
d0 = LENGTH0
a = ANGLE
r = ParamType("r", allow_negative=True)      # dimensionless scalar
b = ParamType("b")                           # boolean
# signed offset "d-" isn't a valid identifier; expose as DMINUS if ever needed.
DMINUS = ParamType("d-", allow_negative=True)


def __getattr__(name):
    # Any unknown ALL-CAPS identifier used as a parameter-type constant
    # resolves to a generic ParamType rather than crashing the import. This
    # future-proofs against Plant type names we haven't catalogued yet.
    if name.isupper():
        return ParamType(name, allow_negative=True)
    raise AttributeError("module 'varmain.custom' has no attribute %r" % name)


def _ensure_meta(fn):
    meta = getattr(fn, "_p3d_meta", None)
    if meta is None:
        meta = {"activate": {}, "params": {}, "groups": [], "enums": {}}
        fn._p3d_meta = meta
    return meta


def activate(**kw):
    def deco(fn):
        _ensure_meta(fn)["activate"] = kw
        return fn
    return deco


def group(name, **kw):
    def deco(fn):
        _ensure_meta(fn)["groups"].append(name)
        return fn
    return deco


def param(**kw):
    # e.g. @param(D=LENGTH, TooltipShort="Diameter", TooltipLong="...")
    def deco(fn):
        meta = _ensure_meta(fn)
        name = None
        ptype = None
        for k, v in kw.items():
            if isinstance(v, ParamType):
                name, ptype = k, v
                break
        if name is None:
            return fn
        meta["params"][name] = {
            "name": name,
            "type": ptype.name,
            "allow_negative": ptype.allow_negative,
            "allow_zero": ptype.allow_zero,
            "short": kw.get("TooltipShort", name),
            "long": kw.get("TooltipLong", ""),
        }
        return fn
    return deco


def enum(**kw):
    def deco(fn):
        meta = _ensure_meta(fn)
        for k, v in kw.items():
            meta["enums"][k] = v
        return fn
    return deco
