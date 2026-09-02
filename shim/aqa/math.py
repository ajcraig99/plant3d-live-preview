"""
Shim for `from aqa.math import *`.

Plant standardises on `aqa.math` rather than Python's `math`. Conventions the
repo scripts rely on:
  * trig functions take RADIANS
  * `asRadiants(deg)` converts degrees -> radians (note Plant's spelling)
  * solid rotateX/Y/Z take degrees (handled in the kernel, not here)

Everything Python's `math` offers is re-exported so a script that reaches for
`log10`, `isclose`, `inf` and so on works. The exact surface of Plant's real
`aqa.math` is [TO CONFIRM]; this is a superset of what the repo scripts use.
"""

from math import *  # noqa: F401,F403
import math as _m


def asRadiants(deg):
    """Degrees -> radians. Matches Plant's (mis)spelled helper name."""
    return _m.radians(deg)


# Common alternate spellings, just in case a script uses them.
asRadians = asRadiants


def asDegrees(rad):
    return _m.degrees(rad)
