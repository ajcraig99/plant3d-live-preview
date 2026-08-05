"""
Shim for `from aqa.math import *`.

Plant standardises on `aqa.math` rather than Python's `math`. Key conventions
the repo scripts rely on:
  * trig functions take RADIANS
  * `asRadiants(deg)` converts degrees -> radians (note Plant's spelling)
  * solid rotateX/Y/Z take degrees (handled in the kernel, not here)
"""

import math as _m

pi = _m.pi
e = _m.e
tau = getattr(_m, "tau", 2 * _m.pi)


def asRadiants(deg):
    """Degrees -> radians. Matches Plant's (mis)spelled helper name."""
    return _m.radians(deg)


# Common alternate spellings, just in case a script uses them.
asRadians = asRadiants


def asDegrees(rad):
    return _m.degrees(rad)


def sin(x):
    return _m.sin(x)


def cos(x):
    return _m.cos(x)


def tan(x):
    return _m.tan(x)


def asin(x):
    return _m.asin(x)


def acos(x):
    return _m.acos(x)


def atan(x):
    return _m.atan(x)


def atan2(y, x):
    return _m.atan2(y, x)


def sqrt(x):
    return _m.sqrt(x)


def pow(x, y):
    return _m.pow(x, y)


def exp(x):
    return _m.exp(x)


def log(x, *base):
    return _m.log(x, *base)


def fabs(x):
    return _m.fabs(x)


def floor(x):
    return _m.floor(x)


def ceil(x):
    return _m.ceil(x)


def hypot(x, y):
    return _m.hypot(x, y)


def degrees(x):
    return _m.degrees(x)


def radians(x):
    return _m.radians(x)
