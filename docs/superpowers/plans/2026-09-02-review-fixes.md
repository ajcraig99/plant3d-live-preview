# Review Fixes and Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement every bug fix, improvement and enhancement from the 2026-09-02 review of plant3d-live-preview, each with a regression test, on a branch.

**Architecture:** The tool has three layers that this plan changes in order: the Python shim that executes Plant 3D scripts on the manifold3d kernel (`shim/`, `render.py`), the stdlib HTTP server with a polling file watcher (`server.py`), and the single-file three.js viewer (`viewer/index.html`). Python layers are covered by `unittest`. The viewer is covered by Playwright end-to-end tests that run the real server in-process and drive headless Chromium; the viewer exposes a small `window.__p3d` hook object purely so tests can observe state.

**Tech Stack:** Python 3.13, manifold3d 3.5.2, trimesh 4.12.2, numpy 2.5.1, scipy 1.18.0 (all pinned in `requirements.txt`), three.js r160 (vendored), Playwright for Python (dev only), GitHub Actions.

---

## Conventions used in every task

- **Branch first.** All work happens on a branch: `git checkout -b review-fixes` before Task 1. Never commit on `main`.
- **Interpreter.** `$PY` means the venv interpreter. On Windows Git Bash: `PY=.venv/Scripts/python.exe`. On Linux: `PY=.venv/bin/python`. Create it once with `py -3 -m venv .venv` (Windows) or `python3 -m venv .venv` (Linux), then `$PY -m pip install -r requirements.txt`.
- **Run all tests.** `$PY -m unittest -v` from the repo root. Discovery picks up every `test_*.py` in the root. Expected at the start of this plan: 10 tests, all OK.
- **Run one test file.** `$PY -m unittest test_shim -v`.
- **Commit messages** follow the existing style in `git log`: a plain imperative sentence, no prefix, e.g. `Warn when a primitive produces empty geometry`.
- **Test script sources** in this plan use `{stem}` for the entry function name and are passed through `textwrap.dedent(...).format(stem=stem)`. Never put literal `{` or `}` in a test script body for that reason.
- **Fidelity facts marked [TO CONFIRM]** are things about the real Plant 3D API that nobody has verified from Autodesk documentation. Implement as written; do not silently "fix" them.

## File map

| File | Responsibility after this plan |
|---|---|
| `shim/p3dkernel.py` | Geometry kernel: `Scene`, `Solid`, primitive constructors, per-scene facet count, empty-geometry warnings, primitive dimension tracking. |
| `shim/varmain/primitiv.py` | Star-import surface for primitives, with `__all__` so unmodelled names fall back to placeholders. |
| `shim/varmain/custom.py` | Decorators and type constants. Unchanged except `__all__`. |
| `shim/aqa/math.py` | Re-exports all of Python `math` plus Plant's `asRadiants`. |
| `render.py` | Loads a script (with sibling imports), describes params (with enums), renders to GLB, records elapsed time and primitive dims. CLI writes `<stem>.glb` and `<stem>.meta.json`. |
| `server.py` | HTTP server. Hardened listing, confined static paths, validated bodies, Condition-based change notification, remote-safety flag, friendly port error, `segments` query param. |
| `viewer/index.html` | The viewer. Request sequencing, no-flash swap, cached meta, typed controls, escaping, URL hash state, on-demand drawing, spin pivot, section cut, measure tool, export and copy buttons, segments select, test hook. |
| `testutil.py` | Shared test helpers: write a script, render a temp script, volume and island count of a GLB. |
| `test_shim.py` | Shim behaviour tests (star import, warnings, math, enums, sibling imports, segments, primitive dims). |
| `test_kernel_primitives.py` | Volume and bounds checks for every modelled primitive and boolean. |
| `test_server_http.py` | Real HTTP requests against an in-process server. |
| `test_server_watcher.py` | Existing watcher tests plus hardening and Condition tests. |
| `test_viewer_e2e.py` | Playwright tests, skipped when Playwright is not installed. |
| `p3dpreview`, `p3dpreview.ps1` | Launchers for Linux/Git Bash and PowerShell. |
| `requirements-dev.txt` | Playwright pin for tests. |
| `.github/workflows/test.yml` | CI on Ubuntu and Windows. |
| `README.md`, `vendor/THIRD_PARTY.md`, `.gitignore` | Docs and housekeeping. |

---

## Phase 1: Test scaffolding

### Task 1: Shared test helpers

**Files:**
- Create: `testutil.py`
- Create: `test_shim.py`

- [ ] **Step 1: Create the branch**

```bash
git checkout -b review-fixes
```

- [ ] **Step 2: Write `testutil.py`**

```python
"""Shared helpers for the test suite. Not a test module (no test_ prefix)."""
import io
import os
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trimesh  # noqa: E402
from render import render_script  # noqa: E402


def write_script(directory, stem, source):
    """Write `source` (dedented, with {stem} substituted) to directory/stem.py
    and return the path."""
    path = os.path.join(directory, stem + ".py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(source).format(stem=stem))
    return path


def render_temp_script(stem, source, params=None, **kw):
    """Render a one-off script from a temp dir. Extra kwargs go to render_script."""
    with tempfile.TemporaryDirectory() as td:
        return render_script(write_script(td, stem, source), params, **kw)


def _glb_mesh(result):
    assert result["glb"], "render produced no GLB"
    loaded = trimesh.load(io.BytesIO(result["glb"]), file_type="glb")
    return loaded.to_geometry() if isinstance(loaded, trimesh.Scene) else loaded


def glb_volume(result):
    return abs(_glb_mesh(result).volume)


def glb_island_count(result):
    return len(_glb_mesh(result).split(only_watertight=False))
```

- [ ] **Step 3: Write `test_shim.py` with a smoke test that uses the helper**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from testutil import render_temp_script  # noqa: E402


class ShimTests(unittest.TestCase):
    def test_helper_renders_a_box(self):
        result = render_temp_script(
            "smoke_box",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                BOX(s, L=20.0, W=10.0, H=6.0)
            """,
        )
        self.assertEqual(result["meta"]["solid_count"], 1)
        self.assertTrue(result["glb"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the new file**

Run: `$PY -m unittest test_shim -v`
Expected: `test_helper_renders_a_box ... ok`, `Ran 1 test`, `OK`

- [ ] **Step 5: Commit**

```bash
git add testutil.py test_shim.py
git commit -m "Add shared test helpers and shim test module"
```

---

## Phase 2: Shim

### Task 2: Unmodelled primitives fall back to a placeholder under star import

**Why:** `from varmain.primitiv import *` copies only names present in the module dict. A module-level `__getattr__` is never consulted for star import unless the name is listed in `__all__`. Today `ARC3D(s, ...)` raises `NameError`.

**Files:**
- Modify: `shim/varmain/primitiv.py`
- Modify: `shim/varmain/custom.py`
- Test: `test_shim.py`

- [ ] **Step 1: Write the failing test** (add inside `ShimTests`)

```python
    def test_unmodelled_primitive_via_star_import_draws_placeholder(self):
        result = render_temp_script(
            "arcpart",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                ARC3D(s, R=50.0, A=90.0)
            """,
        )
        meta = result["meta"]
        self.assertEqual(meta["solid_count"], 1)
        self.assertEqual(len(meta["warnings"]), 1)
        self.assertIn("ARC3D", meta["warnings"][0])
        self.assertIn("placeholder", meta["warnings"][0])

    def test_star_import_does_not_leak_manifold_class(self):
        with self.assertRaises(Exception) as ctx:
            render_temp_script(
                "leakcheck",
                """
                from varmain.primitiv import *
                from varmain.custom import *

                @activate(Group="Test", LengthUnit="mm")
                def {stem}(s, **kw):
                    Manifold.cube([1, 1, 1], True)
                """,
            )
        self.assertIn("NameError", str(ctx.exception))
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim -v`
Expected: the placeholder test FAILS with `RenderError: script raised NameError: name 'ARC3D' is not defined`; the leak test FAILS because `Manifold` currently resolves.

- [ ] **Step 3: Add `__all__` to `shim/varmain/primitiv.py`**

Replace the block from `_UNMODELLED = {` down to the closing `}` with:

```python
_UNMODELLED = {
    "ARC3D", "ARC3D2", "ARC3DS", "PYRAMID", "ROUNDRECT", "SPHERESEGMENT",
    "ELLIPSOIDHEAD2", "ELLIPSOIDSEGMENT", "TORISPHERICHEAD", "TORISPHERICHEAD2",
    "TORISPHERICHEADH", "CORNERBOX", "EQBOX", "EQCONE", "EQCYLINDER",
    "EQHALFSPHERE", "CDBOX", "CDCYLINDER",
}

_MODELLED = ["Solid", "BOX", "CYLINDER", "CONE", "TORUS", "SPHERE", "HALFSPHERE", "ELLIPSOIDHEAD"]

# `from varmain.primitiv import *` only sees names in __all__. Listing the
# unmodelled names here makes star import call __getattr__ below for each of
# them, so scripts get the placeholder instead of a NameError. `Manifold` is
# deliberately not exported.
__all__ = _MODELLED + sorted(_UNMODELLED)
```

- [ ] **Step 4: Add `__all__` to `shim/varmain/custom.py`**

Insert after the line `DMINUS = ParamType("d-", allow_negative=True)`:

```python
__all__ = [
    "ParamType", "LENGTH", "LENGTH0", "ANGLE", "ENUM", "INT", "INTEGER", "BOOL",
    "BOOLEAN", "STRING", "d", "d0", "a", "r", "b", "DMINUS",
    "activate", "group", "param", "enum",
]
```

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest test_shim -v`
Expected: 3 tests OK.

- [ ] **Step 6: Run everything**

Run: `$PY -m unittest -v`
Expected: 13 tests OK.

- [ ] **Step 7: Commit**

```bash
git add shim/varmain/primitiv.py shim/varmain/custom.py test_shim.py
git commit -m "Make unmodelled primitives fall back to a placeholder under star import"
```

### Task 3: Warn when a primitive produces empty geometry

**Files:**
- Modify: `shim/p3dkernel.py`
- Test: `test_shim.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_zero_radius_cylinder_warns_instead_of_vanishing_silently(self):
        result = render_temp_script(
            "zero_cyl",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                CYLINDER(s, R=0.0, H=10.0)
            """,
        )
        meta = result["meta"]
        self.assertEqual(meta["solid_count"], 0)
        self.assertEqual(len(meta["warnings"]), 1)
        self.assertIn("CYLINDER", meta["warnings"][0])
        self.assertIn("no geometry", meta["warnings"][0])
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim.ShimTests.test_zero_radius_cylinder_warns_instead_of_vanishing_silently -v`
Expected: FAIL, `AssertionError: 0 != 1` on the warnings length.

- [ ] **Step 3: Add `_finish` and route every constructor through it**

In `shim/p3dkernel.py`, insert this helper directly above `def BOX(`:

```python
def _finish(s, name, manifold, args):
    """Wrap `manifold` in a Solid and warn if it came out empty, which is what
    happens for zero or negative sizes. A silently missing part is confusing
    in a preview, so say so."""
    solid = Solid(s, manifold)
    if manifold.is_empty():
        desc = ", ".join("%s=%s" % (k, v) for k, v in args.items())
        s.warnings.append(
            "%s(%s) produced no geometry (check for zero or negative sizes)" % (name, desc))
    return solid
```

Then replace the constructors as follows.

`BOX`:
```python
def BOX(s, L=1.0, W=1.0, H=1.0, **kw):
    return _finish(s, "BOX", Manifold.cube([float(H), float(L), float(W)], True),
                   {"L": L, "W": W, "H": H})
```

`CYLINDER` (the bore is subtracted before the emptiness check):
```python
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
    O = float(O or 0.0)
    if O > 0.0:
        bore = Manifold.cylinder(H + 2 * _EPS, O, O, SEGMENTS, False).translate((0, 0, -_EPS))
        outer = outer - bore
    return _finish(s, "CYLINDER", outer, {"R": R, "H": H, "O": O, "R1": R1, "R2": R2})
```

`CONE`:
```python
def CONE(s, R1=1.0, R2=0.0, H=1.0, E=0.0, **kw):
    # E (eccentricity) is 0.0 everywhere in the repo; concentric cone.
    return _finish(s, "CONE", Manifold.cylinder(float(H), float(R1), float(R2), SEGMENTS, False),
                   {"R1": R1, "R2": R2, "H": H})
```

`TORUS`:
```python
def TORUS(s, R1=1.0, R2=0.5, **kw):
    # Ring radius R1, tube radius R2. Revolve a circle; manifold's revolve puts
    # the resulting axis on Z, matching Plant's TORUS (ring in XY plane).
    circle = CrossSection.circle(float(R2), SEGMENTS).translate((float(R1), 0.0))
    return _finish(s, "TORUS", Manifold.revolve(circle, SEGMENTS, 360.0), {"R1": R1, "R2": R2})
```

`SPHERE`:
```python
def SPHERE(s, R=1.0, **kw):
    return _finish(s, "SPHERE", Manifold.sphere(float(R), SEGMENTS), {"R": R})
```

`HALFSPHERE`:
```python
def HALFSPHERE(s, R=1.0, **kw):
    sph = Manifold.sphere(float(R), SEGMENTS)
    # keep the +Z half
    box = Manifold.cube([4 * float(R), 4 * float(R), 4 * float(R)], True).translate((0, 0, 2 * float(R)))
    return _finish(s, "HALFSPHERE", sph ^ box, {"R": R})
```

`ELLIPSOIDHEAD`:
```python
def ELLIPSOIDHEAD(s, R=1.0, H=None, **kw):
    # Approximate a 2:1 ellipsoidal head as a squashed half-sphere.
    r = float(R)
    h = float(H) if H is not None else r / 2.0
    sph = Manifold.sphere(r, SEGMENTS)
    box = Manifold.cube([4 * r, 4 * r, 4 * r], True).translate((0, 0, 2 * r))
    return _finish(s, "ELLIPSOIDHEAD", (sph ^ box).scale((1.0, 1.0, h / r)), {"R": R, "H": h})
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 14 tests OK.

- [ ] **Step 5: Commit**

```bash
git add shim/p3dkernel.py test_shim.py
git commit -m "Warn when a primitive produces empty geometry"
```

### Task 4: `aqa.math` re-exports all of Python's `math`

**Files:**
- Modify: `shim/aqa/math.py`
- Test: `test_shim.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_aqa_math_exposes_full_python_math_surface(self):
        result = render_temp_script(
            "mathuse",
            """
            from varmain.primitiv import *
            from varmain.custom import *
            from aqa.math import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                r = log10(1000.0) * 10.0          # 30
                assert isclose(asRadiants(180.0), pi)
                assert isfinite(hypot(3.0, 4.0, 12.0))
                SPHERE(s, R=r)
            """,
        )
        self.assertEqual(result["meta"]["solid_count"], 1)
        self.assertEqual(result["meta"]["warnings"], [])
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim.ShimTests.test_aqa_math_exposes_full_python_math_surface -v`
Expected: FAIL with `RenderError: script raised NameError: name 'log10' is not defined`.

- [ ] **Step 3: Replace the whole of `shim/aqa/math.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 15 tests OK.

- [ ] **Step 5: Commit**

```bash
git add shim/aqa/math.py test_shim.py
git commit -m "Re-export all of Python math from the aqa.math shim"
```

### Task 5: Surface enum options and keep non-numeric defaults in the param schema

**Files:**
- Modify: `render.py:72-95` (`describe_params`)
- Test: `test_shim.py`

**Fidelity note [TO CONFIRM]:** the shim accepts `@enum(NAME=[...])` because `varmain/custom.py` stores whatever keyword arguments `enum(...)` receives. The real Plant syntax for enum declarations has not been confirmed from Autodesk documentation. Implement against the shim's existing acceptance.

- [ ] **Step 1: Write the failing test**

```python
    def test_describe_params_surfaces_enum_options_and_typed_defaults(self):
        result = render_temp_script(
            "enumpart",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            @param(KIND=ENUM, TooltipShort="Kind")
            @enum(KIND=["A", "B", "C"])
            @param(FLAG=BOOL, TooltipShort="Flag")
            @param(TAG=STRING, TooltipShort="Tag")
            @param(D=LENGTH, TooltipShort="Diameter")
            def {stem}(s, KIND="A", FLAG=True, TAG="x", D=20.0, **kw):
                SPHERE(s, R=D / 2.0)
            """,
        )
        by_name = {p["name"]: p for p in result["meta"]["params"]}
        self.assertEqual(by_name["KIND"]["enum"], ["A", "B", "C"])
        self.assertEqual(by_name["KIND"]["default"], "A")
        self.assertIsNone(by_name["D"]["enum"])
        self.assertIs(by_name["FLAG"]["default"], True)
        self.assertEqual(by_name["TAG"]["default"], "x")
        self.assertEqual(by_name["D"]["type"], "LENGTH")
        self.assertFalse(by_name["D"]["allow_zero"])
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim.ShimTests.test_describe_params_surfaces_enum_options_and_typed_defaults -v`
Expected: FAIL with `KeyError: 'enum'`.

- [ ] **Step 3: Update `describe_params` in `render.py`**

Replace the function with:

```python
def describe_params(fn):
    """Merge @param metadata with the function signature defaults into an
    ordered list the UI can render."""
    meta = getattr(fn, "_p3d_meta", {}) or {}
    pmeta = meta.get("params", {})
    enums = meta.get("enums", {})
    sig = inspect.signature(fn)
    out = []
    for i, (name, sp) in enumerate(sig.parameters.items()):
        if i == 0:
            continue  # the scene 's'
        if sp.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        default = sp.default if sp.default is not inspect.Parameter.empty else 0.0
        info = pmeta.get(name, {})
        options = enums.get(name)
        if isinstance(options, dict):
            options = list(options.keys())
        out.append({
            "name": name,
            "default": default,
            "type": info.get("type", "LENGTH"),
            "short": info.get("short", name),
            "long": info.get("long", ""),
            "allow_negative": info.get("allow_negative", False),
            "allow_zero": info.get("allow_zero", True),
            "enum": [str(o) for o in options] if options else None,
        })
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 16 tests OK.

- [ ] **Step 5: Commit**

```bash
git add render.py test_shim.py
git commit -m "Surface enum options in the parameter schema"
```

### Task 6: Scripts can import sibling helper modules, and edits to helpers are picked up

**Files:**
- Modify: `render.py:45-69` (`_load_entry`)
- Test: `test_shim.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_script_can_import_sibling_helper_and_sees_helper_edits(self):
        import tempfile
        from testutil import write_script
        from render import render_script
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "helper_sizes.py"), "w") as f:
                f.write("SIZE = 20.0\n")
            path = write_script(td, "usehelper", """
                from varmain.primitiv import *
                from varmain.custom import *
                from helper_sizes import SIZE

                @activate(Group="Test", LengthUnit="mm")
                def {stem}(s, **kw):
                    BOX(s, L=SIZE, W=10.0, H=6.0)
                """)
            first = render_script(path)["meta"]["bounds"]
            # BOX L runs along Plant Y, which the exporter maps to viewer -Z.
            self.assertAlmostEqual(first["max"][2] - first["min"][2], 20.0, places=5)

            with open(os.path.join(td, "helper_sizes.py"), "w") as f:
                f.write("SIZE = 40.0\n")
            second = render_script(path)["meta"]["bounds"]
            self.assertAlmostEqual(second["max"][2] - second["min"][2], 40.0, places=5)
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim.ShimTests.test_script_can_import_sibling_helper_and_sees_helper_edits -v`
Expected: ERROR with a raw `ModuleNotFoundError: No module named 'helper_sizes'`. Today `exec_module` failures are not wrapped in `RenderError`; the server only survives them thanks to its generic `except Exception`. Step 3 wraps them so the banner gets a proper message.

- [ ] **Step 3: Rewrite `_load_entry` in `render.py`**

```python
def _purge_modules_from(directory):
    """Drop cached modules whose source lives in `directory`, so that a helper
    module edited between renders is re-imported. The tool's own directories
    are never purged."""
    if directory in (_HERE, _SHIM):
        return
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if f and os.path.dirname(os.path.abspath(f)) == directory:
            del sys.modules[name]


def _load_entry(path):
    """Import the script module and return (module, entry_function)."""
    path = os.path.abspath(path)
    script_dir = os.path.dirname(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    modname = "p3d_script_" + stem
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RenderError("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    _purge_modules_from(script_dir)
    sys.modules[modname] = mod
    # Let the script import helpers that sit next to it, like Plant does when
    # the folder is on its script path.
    sys.path.insert(0, script_dir)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        import traceback
        raise RenderError("script failed to import: %s: %s\n%s" % (
            type(e).__name__, e, traceback.format_exc()))
    finally:
        try:
            sys.path.remove(script_dir)
        except ValueError:
            pass

    # Prefer a function whose name matches the filename (Plant's rule).
    fn = getattr(mod, stem, None)
    if callable(fn) and hasattr(fn, "_p3d_meta"):
        return mod, fn
    # Otherwise take the first function carrying Plant metadata.
    for name, obj in vars(mod).items():
        if callable(obj) and hasattr(obj, "_p3d_meta"):
            return mod, obj
    if callable(fn):
        return mod, fn
    raise RenderError(
        "no entry function found in %s (expected a function named '%s' "
        "decorated with @activate)" % (os.path.basename(path), stem))
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 17 tests OK.

- [ ] **Step 5: Commit**

```bash
git add render.py test_shim.py
git commit -m "Let scripts import sibling helpers and re-import them on each render"
```

### Task 7: Facet count per scene, selectable per render

**Files:**
- Modify: `shim/p3dkernel.py` (`Scene.__init__`, every `SEGMENTS` use in constructors)
- Modify: `render.py` (`render_script` signature, meta)
- Test: `test_shim.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_segments_argument_controls_mesh_density(self):
        src = """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                CYLINDER(s, R=10.0, H=20.0)
            """
        coarse = render_temp_script("segcyl", src, segments=16)
        fine = render_temp_script("segcyl", src, segments=96)
        self.assertEqual(coarse["meta"]["segments"], 16)
        self.assertEqual(fine["meta"]["segments"], 96)
        self.assertLess(len(coarse["glb"]), len(fine["glb"]))
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim.ShimTests.test_segments_argument_controls_mesh_density -v`
Expected: FAIL with `TypeError: render_script() got an unexpected keyword argument 'segments'`.

- [ ] **Step 3: Give `Scene` a `segments` attribute**

In `shim/p3dkernel.py`, replace `Scene.__init__`:

```python
    def __init__(self, segments=None):
        self.segments = int(segments) if segments else SEGMENTS
        self.solids = []        # every Solid ever created, in creation order
        self.points = []        # {'pos':(x,y,z), 'dir':(dx,dy,dz), 'extra':(...)}
        self.dims = []          # {'name':str, 'a':(x,y,z), 'b':(x,y,z)}
        self.warnings = []      # stubbed / unknown API calls, surfaced to user
```

Then in every constructor replace `SEGMENTS` with `s.segments`. There are eight occurrences: two in `CYLINDER` (outer) plus one (bore), one in `CONE`, two in `TORUS`, one in `SPHERE`, one in `HALFSPHERE`, one in `ELLIPSOIDHEAD`. Verify with:

Run: `grep -n "SEGMENTS" shim/p3dkernel.py`
Expected: only the module-level `SEGMENTS = int(os.environ.get(...))` line and the `Scene.__init__` line remain.

- [ ] **Step 4: Thread `segments` through `render_script`**

In `render.py`, change the signature and the `Scene()` call, and add `segments` to `meta`:

```python
def render_script(path, params=None, segments=None):
    """Run the script and return a dict with keys:
        glb   : bytes (GLB) or None if empty
        meta  : dict (params schema, values used, ports, dims, warnings, bounds)
    `segments` overrides the facet count for round primitives (default from
    P3D_SEGMENTS env, else 96).
    Raises RenderError on load/exec failure (message is user-facing)."""
    mod, fn = _load_entry(path)
    schema = describe_params(fn)
    values = {p["name"]: p["default"] for p in schema}
    if params:
        for k, v in params.items():
            if k in values:
                values[k] = v

    s = Scene(segments=segments)
```

and in the `meta = {` dict add after `"bounds": bounds,`:

```python
        "segments": s.segments,
```

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 18 tests OK.

- [ ] **Step 6: Commit**

```bash
git add shim/p3dkernel.py render.py test_shim.py
git commit -m "Make the facet count a per-render setting"
```

### Task 8: Track primitive dimensions on each solid (backs the "Fixed dims" button)

**Why:** the viewer already draws `meta.primitive_dims` (green lines labelled `PRIMITIVE.name=len`) but nothing produces them. Each constructor records its defining lengths in local coordinates; transforms move them with the solid; consumed or erased solids drop out.

**Files:**
- Modify: `shim/p3dkernel.py`
- Modify: `render.py` (meta)
- Test: `test_shim.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_primitive_dims_follow_translation(self):
        result = render_temp_script(
            "dimbox",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                BOX(s, L=20.0, W=10.0, H=6.0).translate((30.0, -20.0, 40.0))
            """,
        )
        dims = {d["name"]: d for d in result["meta"]["primitive_dims"]}
        self.assertEqual(set(dims), {"L", "W", "H"})
        self.assertEqual(dims["H"]["primitive"], "BOX")
        # corner of the box after translation: (30-3, -20-10, 40-5)
        self.assertEqual(tuple(dims["H"]["a"]), (27.0, -30.0, 35.0))
        self.assertEqual(tuple(dims["H"]["b"]), (33.0, -30.0, 35.0))
        self.assertEqual(tuple(dims["L"]["b"]), (27.0, -10.0, 35.0))
        self.assertEqual(tuple(dims["W"]["b"]), (27.0, -30.0, 45.0))

    def test_primitive_dims_follow_rotation_and_drop_consumed_operands(self):
        result = render_temp_script(
            "dimrot",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                main = BOX(s, L=20.0, W=10.0, H=6.0).rotateZ(90)
                cutter = CYLINDER(s, R=2.0, H=30.0).translate((0.0, 0.0, -15.0))
                main.subtractFrom(cutter)
                cutter.erase()
            """,
        )
        dims = {d["name"]: d for d in result["meta"]["primitive_dims"]}
        self.assertEqual(set(dims), {"L", "W", "H"})   # cutter's R/H are gone
        a, b = dims["H"]["a"], dims["H"]["b"]
        # corner (-3,-10,-5) rotated 90 about Z -> (10,-3,-5); end (3,-10,-5) -> (10,3,-5)
        for got, want in zip(a, (10.0, -3.0, -5.0)):
            self.assertAlmostEqual(got, want, places=9)
        for got, want in zip(b, (10.0, 3.0, -5.0)):
            self.assertAlmostEqual(got, want, places=9)

    def test_round_primitives_record_radius_and_height_dims(self):
        result = render_temp_script(
            "dimround",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                CYLINDER(s, R=10.0, H=20.0, O=4.0)
                CONE(s, R1=10.0, R2=5.0, H=8.0).translate((50.0, 0.0, 0.0))
                TORUS(s, R1=30.0, R2=3.0).translate((100.0, 0.0, 0.0))
                SPHERE(s, R=7.0).translate((150.0, 0.0, 0.0))
            """,
        )
        names = sorted((d["primitive"], d["name"]) for d in result["meta"]["primitive_dims"])
        self.assertEqual(names, [
            ("CONE", "H"), ("CONE", "R1"), ("CONE", "R2"),
            ("CYLINDER", "H"), ("CYLINDER", "O"), ("CYLINDER", "R"),
            ("SPHERE", "R"),
            ("TORUS", "R1"), ("TORUS", "R2"),
        ])
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim -v`
Expected: the three new tests FAIL with `KeyError: 'primitive_dims'`.

- [ ] **Step 3: Add dimension tracking to `Solid`**

In `shim/p3dkernel.py` add `import math` next to `import os` at the top, then add this helper above `class Scene`:

```python
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
```

Add to `Scene`, after `live_solids`:

```python
    def primitive_dims(self):
        """Defining lengths of every live primitive, in world coordinates,
        as [{'primitive','name','a','b'}]. Feeds the viewer's Fixed dims."""
        return [
            {"primitive": s.primitive, "name": d["name"], "a": d["a"], "b": d["b"]}
            for s in self.live_solids() for d in s.dims
        ]
```

Replace the `Solid` class header, slots, `__init__`, and transform methods:

```python
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
```

Leave the boolean, lifecycle and query methods exactly as they are.

- [ ] **Step 4: Record dims in `_finish` and every constructor**

Replace `_finish`:

```python
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
```

Replace the constructors:

```python
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
```

The placeholder in `shim/varmain/primitiv.py` constructs `Solid(s, Manifold.cube(...))` directly; change that line to `return Solid(s, Manifold.cube([hint, hint, hint], True), primitive=name)`.

- [ ] **Step 5: Emit `primitive_dims` from `render.py`**

In the `meta = {` dict, after `"dims": s.dims,` add:

```python
        "primitive_dims": s.primitive_dims(),
```

- [ ] **Step 6: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 21 tests OK.

- [ ] **Step 7: Commit**

```bash
git add shim/p3dkernel.py shim/varmain/primitiv.py render.py test_shim.py
git commit -m "Track primitive dimensions through transforms and emit them as primitive_dims"
```

---

## Phase 3: Server

### Task 9: Script discovery and the watcher survive unreadable folders

**Files:**
- Modify: `server.py:60-96, 130-142`
- Test: `test_server_watcher.py`

- [ ] **Step 1: Write the failing tests** (add a new class to `test_server_watcher.py`; add `import tempfile` and `from unittest import mock` at the top)

```python
class DiscoveryHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d, name in (("alpha", "a.py"), ("locked", "b.py")):
            os.makedirs(os.path.join(self.root, d))
            open(os.path.join(self.root, d, name), "w").close()
        open(os.path.join(self.root, "top.py"), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def _listdir_denying(self, denied_suffix):
        real = os.listdir

        def fake(path="."):
            if str(path).replace("\\", "/").endswith(denied_suffix):
                raise PermissionError(13, "Access is denied", str(path))
            return real(path)
        return fake

    def test_discover_scripts_skips_unreadable_subfolder(self):
        with mock.patch("server.os.listdir", side_effect=self._listdir_denying("/locked")):
            self.assertEqual(server.discover_scripts(self.root), ["top.py", "alpha/a.py"])

    def test_discover_scripts_returns_empty_for_unreadable_root(self):
        with mock.patch("server.os.listdir", side_effect=PermissionError(13, "denied")):
            self.assertEqual(server.discover_scripts(self.root), [])

    def test_dir_entries_survive_unreadable_children(self):
        with mock.patch("server.os.listdir", side_effect=self._listdir_denying("/locked")):
            entries = {e["name"]: e["has_scripts"] for e in server._dir_entries(self.root)}
        self.assertEqual(entries, {"alpha": True, "locked": False})

    def test_watch_poll_swallows_errors(self):
        # _watch_poll is one iteration of the watcher loop; it must never raise.
        with mock.patch("server._snapshot", side_effect=RuntimeError("disk went away")):
            self.assertEqual(server._watch_poll({}), {})
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_server_watcher -v`
Expected: the first three FAIL with `PermissionError`; the fourth FAILS with `AttributeError: module 'server' has no attribute '_watch_poll'`.

- [ ] **Step 3: Rewrite discovery and the watcher loop in `server.py`**

Replace `discover_scripts`, `_script_mtimes`, `_watch_change` and `watcher` with:

```python
def _list_py(path):
    """Names of .py files directly inside `path`; [] if it cannot be read."""
    try:
        return sorted(n for n in os.listdir(path) if n.endswith(".py"))
    except OSError:
        return []


def discover_scripts(root=None):
    root = root if root is not None else ROOT
    found = list(_list_py(root))
    for d in _script_subdirs(root):
        found.extend(d + "/" + name for name in _list_py(os.path.join(root, d)))
    return found


def _snapshot():
    """(root, {abs_path: mtime}) for every script under the current root. The
    root is captured alongside so a root switch mid-poll cannot mix paths from
    two trees."""
    root = ROOT
    mtimes = {}
    for rel in discover_scripts(root):
        path = os.path.join(root, rel)
        try:
            mtimes[path] = os.path.getmtime(path)
        except OSError:
            pass  # the file may have disappeared between listing and stat
    return root, mtimes


def _script_mtimes():
    """Kept for callers/tests that only want the mtime map."""
    return _snapshot()[1]


def _watch_change(previous, current, root=None):
    """Describe a snapshot change for the browser's live-reload handler."""
    root = root if root is not None else ROOT
    if previous.keys() != current.keys():
        return "__scripts__"
    for path in sorted(current):
        if previous[path] != current[path]:
            return os.path.relpath(path, root).replace(os.sep, "/")
    return None


def _watch_poll(mtimes):
    """One watcher iteration. Returns the new mtime map. Never raises: a bad
    poll (permission error, unplugged drive) must not kill live reload."""
    try:
        root, current = _snapshot()
        changed = _watch_change(mtimes, current, root)
        if changed:
            _notify(changed)
        return current
    except Exception as e:
        print("[watcher] %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return mtimes


def _notify(changed):
    global _watch_version, _last_changed
    with _watch_lock:
        _watch_version += 1
        _last_changed = changed


def watcher():
    """Poll scripts; notify clients about edits, additions, and deletions."""
    mtimes = _snapshot()[1]
    while True:
        mtimes = _watch_poll(mtimes)
        time.sleep(0.3)
```

Also update `_handle_set_root` to use `_notify`:

```python
        ROOT = path
        _notify("__root__")
        self._send(200, json.dumps({"root": ROOT, "scripts": discover_scripts()}))
```

(remove the `with _watch_lock:` block and the inner `global` line there).

Update the `_dir_entries` docstring to match reality:

```python
def _dir_entries(path):
    """Subdirectories of `path`, flagged with whether they'd work as a root
    (i.e. contain .py files directly or one level down)."""
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 25 tests OK.

- [ ] **Step 5: Commit**

```bash
git add server.py test_server_watcher.py
git commit -m "Keep script discovery and the watcher alive across unreadable folders"
```

### Task 10: HTTP test harness, confined static paths, validated request bodies

**Files:**
- Create: `test_server_http.py`
- Modify: `server.py` (`do_GET` static branch, `_read_json_body`, `_handle_set_root`, `_handle_render`)

- [ ] **Step 1: Write the harness and failing tests**

```python
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server  # noqa: E402
from testutil import write_script  # noqa: E402

PLATE = """
    from varmain.primitiv import *
    from varmain.custom import *

    @activate(Group="Test", LengthUnit="mm")
    @param(L=LENGTH, TooltipShort="Length")
    def {stem}(s, L=20.0, **kw):
        BOX(s, L=L, W=10.0, H=6.0)
    """


class ServerTestCase(unittest.TestCase):
    """Runs the real Handler on a random loopback port against a temp root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = cls.tmp.name
        os.makedirs(os.path.join(cls.root, "customsupports"))
        write_script(os.path.join(cls.root, "customsupports"), "plate", PLATE)
        cls._saved_root = server.ROOT
        server.ROOT = cls.root
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.ROOT = cls._saved_root
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def get(self, path):
        return self.request("GET", path)

    def post_raw(self, path, raw):
        return self.request("POST", path, body=raw, headers={"Content-Type": "application/json"})


class StaticAndBodyTests(ServerTestCase):
    def test_vendor_file_is_served(self):
        status, data = self.get("/vendor/three.module.js")
        self.assertEqual(status, 200)
        self.assertIn(b"REVISION", data)

    def test_dot_dot_traversal_out_of_vendor_is_refused(self):
        status, _ = self.get("/vendor/../server.py")
        self.assertEqual(status, 403)

    def test_viewer_dir_is_also_confined(self):
        status, _ = self.get("/viewer/../render.py")
        self.assertEqual(status, 403)

    def test_post_root_with_non_object_body_is_400(self):
        status, data = self.post_raw("/api/root", b"[1, 2]")
        self.assertEqual(status, 400)
        self.assertIn("object", json.loads(data)["error"])

    def test_post_root_with_invalid_json_is_400(self):
        status, _ = self.post_raw("/api/root", b"{not json")
        self.assertEqual(status, 400)

    def test_render_with_non_object_params_still_renders(self):
        status, data = self.get("/api/render?script=customsupports/plate.py&params=%5B1%5D")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertNotIn("error", payload)
        self.assertEqual(payload["meta"]["values"]["L"], 20.0)

    def test_render_applies_params(self):
        status, data = self.get("/api/render?script=customsupports/plate.py&params=%7B%22L%22%3A40%7D")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["meta"]["values"]["L"], 40)

    def test_render_refuses_path_outside_root(self):
        status, data = self.get("/api/render?script=../server.py")
        self.assertEqual(status, 400)
        self.assertIn("escapes root", json.loads(data)["error"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_server_http -v`
Expected: traversal tests FAIL (`200 != 403`); non-object body test FAILS with `http.client.RemoteDisconnected` (the handler crashes); the other four pass.

- [ ] **Step 3: Confine static paths in `server.py`**

Add this module-level function below `_safe_script_path`:

```python
def _static_path(url_path):
    """Map /vendor/... or /viewer/... to a file under that folder, or None if
    the normalised path escapes it."""
    parts = [p for p in url_path.split("/") if p]
    if not parts:
        return None
    base = os.path.join(_HERE, parts[0])
    full = os.path.normpath(os.path.join(_HERE, *parts))
    try:
        if os.path.commonpath([base, full]) != base:
            return None
    except ValueError:  # different drives on Windows
        return None
    return full
```

Replace the static branch in `do_GET`:

```python
        elif path.startswith("/vendor/") or path.startswith("/viewer/"):
            full = _static_path(path)
            if full is None:
                self._send(403, "forbidden", "text/plain"); return
            ctype = "application/javascript" if full.endswith(".js") else "text/plain"
            self._send_file(full, ctype)
```

- [ ] **Step 4: Validate request bodies and params**

Replace `_read_json_body`:

```python
    def _read_json_body(self):
        """Parse the JSON body. Raises ValueError (which JSONDecodeError
        subclasses) when the body is not a JSON object."""
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        payload = json.loads(raw or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload
```

In `_handle_set_root` change the `except json.JSONDecodeError:` line to:

```python
        except ValueError as e:
            self._send(400, json.dumps({"error": "invalid JSON body: %s" % e})); return
```

In `_handle_render` replace the params block:

```python
        params = {}
        if q.get("params"):
            try:
                parsed = json.loads(q["params"][0])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                params = parsed
```

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 33 tests OK.

- [ ] **Step 6: Commit**

```bash
git add server.py test_server_http.py
git commit -m "Confine static file paths and validate JSON request bodies"
```

### Task 11: Push change events immediately with a Condition; lock root switches

**Files:**
- Modify: `server.py` (state block, `_notify`, `_handle_set_root`, `_handle_events`)
- Test: `test_server_watcher.py`

- [ ] **Step 1: Write the failing test** (add to `test_server_watcher.py`; add `import threading`, `import time` at the top)

```python
class NotifyTests(unittest.TestCase):
    def test_notify_wakes_a_waiting_event_stream_immediately(self):
        woke = []

        def waiter():
            with server._watch_cond:
                start = server._watch_version
                server._watch_cond.wait_for(lambda: server._watch_version != start, timeout=5.0)
                woke.append(time.monotonic())

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        fired = time.monotonic()
        server._notify("customsupports/one.py")
        t.join(timeout=6.0)
        self.assertEqual(len(woke), 1)
        self.assertLess(woke[0] - fired, 0.5)
        with server._watch_lock:
            self.assertEqual(server._last_changed, "customsupports/one.py")

    def test_set_root_changes_root_under_lock_and_notifies(self):
        saved = server.ROOT
        try:
            before = server._watch_version
            server._set_root(os.path.dirname(os.path.abspath(__file__)))
            self.assertEqual(server.ROOT, os.path.dirname(os.path.abspath(__file__)))
            self.assertEqual(server._watch_version, before + 1)
            self.assertEqual(server._last_changed, "__root__")
        finally:
            server.ROOT = saved
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_server_watcher.NotifyTests -v`
Expected: FAIL with `AttributeError: module 'server' has no attribute '_watch_cond'` and `... '_set_root'`.

- [ ] **Step 3: Add the Condition and `_set_root`**

In the config/state block of `server.py`, replace `_watch_lock = threading.Lock()` with:

```python
_watch_lock = threading.Lock()
_watch_cond = threading.Condition(_watch_lock)   # notifies SSE streams instantly
```

Replace `_notify`:

```python
def _notify(changed):
    global _watch_version, _last_changed
    with _watch_cond:
        _watch_version += 1
        _last_changed = changed
        _watch_cond.notify_all()


def _set_root(path):
    """Switch the watched root. Taken under the watch lock so a poll never
    sees a half-switched state, then broadcast to clients."""
    global ROOT
    with _watch_cond:
        ROOT = path
    _notify("__root__")
```

In `_handle_set_root` replace the two lines `ROOT = path` and `_notify("__root__")` with `_set_root(path)` and delete the `global ROOT` line at the top of that method.

Replace the body of `_handle_events` after `end_headers()`:

```python
        last = -1
        try:
            while True:
                with _watch_cond:
                    if _watch_version == last:
                        # Woken by _notify, or every 15 s for a heartbeat so
                        # proxies / the client keep the stream open.
                        _watch_cond.wait(timeout=15.0)
                    v, ch = _watch_version, _last_changed
                if v != last:
                    last = v
                    payload = json.dumps({"version": v, "changed": ch})
                    self.wfile.write(("data: %s\n\n" % payload).encode())
                else:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 35 tests OK.

- [ ] **Step 5: Commit**

```bash
git add server.py test_server_watcher.py
git commit -m "Push live-reload events immediately and lock root switches"
```

### Task 12: Remote-safety flag, friendly port error, browser URL, `segments` and `elapsed_ms`

**Files:**
- Modify: `server.py` (`_handle_browse`, `_handle_set_root`, `_handle_render`, `main`)
- Modify: `render.py` (`render_script` timing)
- Test: `test_server_http.py`, `test_shim.py`

- [ ] **Step 1: Write the failing tests**

In `test_server_http.py` add:

```python
class RemoteSafetyAndRenderOptionsTests(ServerTestCase):
    def test_browse_and_root_refused_when_root_changes_disabled(self):
        saved = server.ALLOW_ROOT_CHANGE
        server.ALLOW_ROOT_CHANGE = False
        try:
            status, data = self.get("/api/browse?path=" + self.root)
            self.assertEqual(status, 403)
            self.assertIn("--allow-remote-root", json.loads(data)["error"])
            status, _ = self.post_raw("/api/root", json.dumps({"path": self.root}).encode())
            self.assertEqual(status, 403)
        finally:
            server.ALLOW_ROOT_CHANGE = saved

    def test_browse_allowed_by_default(self):
        status, data = self.get("/api/browse?path=" + self.root)
        self.assertEqual(status, 200)
        names = [e["name"] for e in json.loads(data)["entries"]]
        self.assertEqual(names, ["customsupports"])

    def test_render_reports_elapsed_and_honours_segments(self):
        status, data = self.get("/api/render?script=customsupports/plate.py&segments=16")
        self.assertEqual(status, 200)
        meta = json.loads(data)["meta"]
        self.assertEqual(meta["segments"], 16)
        self.assertGreaterEqual(meta["elapsed_ms"], 0.0)

    def test_segments_is_clamped_and_bad_values_ignored(self):
        _, data = self.get("/api/render?script=customsupports/plate.py&segments=100000")
        self.assertEqual(json.loads(data)["meta"]["segments"], 256)
        _, data = self.get("/api/render?script=customsupports/plate.py&segments=abc")
        self.assertEqual(json.loads(data)["meta"]["segments"], server.R.Scene().segments)


class MainTests(unittest.TestCase):
    def test_browser_url_uses_loopback_when_bound_to_all_interfaces(self):
        self.assertEqual(server._browser_url("0.0.0.0", 8770), "http://127.0.0.1:8770/")
        self.assertEqual(server._browser_url("::", 8770), "http://127.0.0.1:8770/")
        self.assertEqual(server._browser_url("192.168.1.5", 8770), "http://192.168.1.5:8770/")

    def test_root_changes_disabled_for_non_loopback_hosts(self):
        self.assertTrue(server._root_changes_allowed("127.0.0.1", False))
        self.assertTrue(server._root_changes_allowed("localhost", False))
        self.assertFalse(server._root_changes_allowed("0.0.0.0", False))
        self.assertTrue(server._root_changes_allowed("0.0.0.0", True))

    def test_port_in_use_is_reported_not_raised(self):
        # Simulate the bind failure rather than really double-binding: with
        # SO_REUSEADDR set by HTTPServer, Windows may let a second bind succeed
        # and main() would then block in serve_forever.
        saved_root, saved_allow = server.ROOT, server.ALLOW_ROOT_CHANGE
        try:
            with mock.patch("server.ThreadingHTTPServer",
                            side_effect=OSError(98, "Address already in use")):
                code = server.main(["--port", "8770", "--no-open", "--root", os.path.dirname(__file__)])
            self.assertEqual(code, 1)
        finally:
            server.ROOT, server.ALLOW_ROOT_CHANGE = saved_root, saved_allow
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_server_http -v`
Expected: new tests FAIL with `AttributeError` on `ALLOW_ROOT_CHANGE`, `_browser_url`, `_root_changes_allowed`; the port test raises `OSError` instead of returning 1; `elapsed_ms` KeyError.

- [ ] **Step 3: Record elapsed time in `render.py`**

At the top of `render.py` add `import time`. In `render_script`, wrap the entry call:

```python
    s = Scene(segments=segments)
    t0 = time.perf_counter()
    try:
        fn(s, **values)
    except Exception as e:
        import traceback
        raise RenderError("script raised %s: %s\n%s" % (
            type(e).__name__, e, traceback.format_exc()))
```

and after the GLB export block (just before `meta = {`), add:

```python
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
```

and in `meta` add `"elapsed_ms": elapsed_ms,` after `"segments": s.segments,`.

- [ ] **Step 4: Add the flag, helpers and `segments` parsing to `server.py`**

In the state block add:

```python
ALLOW_ROOT_CHANGE = True   # main() turns this off for non-loopback binds
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
```

Add module-level helpers below `_static_path`:

```python
def _root_changes_allowed(host, allow_remote_root):
    """Browsing the filesystem and switching root are only safe from the local
    machine. On a LAN bind they are off unless explicitly re-enabled."""
    return host in _LOOPBACK_HOSTS or bool(allow_remote_root)


def _browser_url(host, port):
    open_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return "http://%s:%d/" % (open_host, port)


def _parse_segments(q):
    """Facet count from the query string, clamped to [8, 256]; None if absent
    or not an integer."""
    raw = (q.get("segments") or [""])[0]
    try:
        return max(8, min(256, int(raw)))
    except ValueError:
        return None
```

At the top of `_handle_browse` and `_handle_set_root` add:

```python
        if not ALLOW_ROOT_CHANGE:
            self._send(403, json.dumps({
                "error": "browsing and root changes are disabled on a non-loopback bind; "
                         "start with --allow-remote-root to enable"})); return
```

In `_handle_render` change the render call to:

```python
            result = R.render_script(full, params, segments=_parse_segments(q))
```

Replace `main`:

```python
def main(argv):
    global ROOT, ALLOW_ROOT_CHANGE
    import argparse
    ap = argparse.ArgumentParser(description="Plant 3D live preview server.")
    ap.add_argument("--root", default=ROOT, help="folder containing your Plant 3D custom scripts")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    ap.add_argument("--allow-remote-root", action="store_true",
                    help="allow folder browsing / root switching when bound to a non-loopback host")
    args = ap.parse_args(argv)
    ROOT = os.path.abspath(args.root)
    ALLOW_ROOT_CHANGE = _root_changes_allowed(args.host, args.allow_remote_root)

    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print("Cannot listen on %s:%d (%s). Is another preview server running? "
              "Try --port with a different number." % (args.host, args.port, e.strerror or e),
              file=sys.stderr)
        return 1

    threading.Thread(target=watcher, daemon=True).start()
    url = _browser_url(args.host, args.port)
    print("Plant 3D preview server running at", url)
    print("Watching:", ROOT)
    if not ALLOW_ROOT_CHANGE:
        print("Folder browsing / root switching disabled (non-loopback bind). "
              "Use --allow-remote-root to enable.")
    print("Ctrl-C to stop.")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Update the module docstring line `GET /api/render?script=REL&params=JSON   -> {meta, glb_b64}` to `GET /api/render?script=REL&params=JSON&segments=N   -> {meta, glb_b64}` and the `python server.py` usage lines to mention `--allow-remote-root`.

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: 42 tests OK.

- [ ] **Step 6: Commit**

```bash
git add server.py render.py test_server_http.py
git commit -m "Disable root switching on LAN binds, report port clashes, add segments and elapsed_ms"
```

---

## Phase 4: Viewer

All viewer tasks edit `viewer/index.html`. Line numbers refer to the file as committed at the start of this plan (678 lines); once edits begin, locate code by the quoted snippets, not by line.

### Task 13: Playwright end-to-end harness and test hook

**Files:**
- Create: `requirements-dev.txt`
- Create: `test_viewer_e2e.py`
- Modify: `viewer/index.html` (add `window.__p3d` hook, set `lastMeta`)

- [ ] **Step 1: Install Playwright into the venv and pin it**

```bash
$PY -m pip install playwright
$PY -m playwright install chromium
$PY -m pip freeze | grep -i "^playwright=="
```

Take the exact `playwright==X.Y.Z` line printed by the last command and write it into `requirements-dev.txt`:

```
# Development / test only. Runtime deps live in requirements.txt.
-r requirements.txt
playwright==X.Y.Z   # replace with the version printed by pip freeze; then: python -m playwright install chromium
```

- [ ] **Step 2: Write the harness with one smoke test**

```python
"""End-to-end viewer tests. The real server runs in-process on a random port
against a temp root; headless Chromium drives the page. Skipped entirely when
Playwright is not installed (pip install -r requirements-dev.txt, then
python -m playwright install chromium)."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server  # noqa: E402
from testutil import write_script  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

PLATE = """
    from varmain.primitiv import *
    from varmain.custom import *

    @activate(Group="Test", LengthUnit="mm", TooltipShort="<b>Plate</b>")
    @param(L=LENGTH, TooltipShort="Length")
    @param(W=LENGTH, TooltipShort="Width")
    def {stem}(s, L=20.0, W=10.0, **kw):
        BOX(s, L=L, W=W, H=6.0)
        s.setPoint((0.0, -L / 2.0, 0.0), (0.0, -1.0, 0.0))
        s.setLinearDimension("L", (-3.0, -L / 2.0, 0.0), (-3.0, L / 2.0, 0.0))
    """

BROKEN = """
    from varmain.primitiv import *
    from varmain.custom import *

    @activate(Group="Test", LengthUnit="mm")
    def {stem}(s, **kw):
        raise ValueError("boom from the script")
    """

ENUMPART = """
    from varmain.primitiv import *
    from varmain.custom import *

    @activate(Group="Test", LengthUnit="mm")
    @param(KIND=ENUM, TooltipShort="Kind")
    @enum(KIND=["A", "B"])
    @param(FLAG=BOOL, TooltipShort="Flag")
    @param(D=LENGTH, TooltipShort="Diameter")
    def {stem}(s, KIND="A", FLAG=True, D=20.0, **kw):
        SPHERE(s, R=D / 2.0 if FLAG else D / 4.0)
    """


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class ViewerE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = cls.tmp.name
        cls.scripts_dir = os.path.join(cls.root, "customsupports")
        os.makedirs(cls.scripts_dir)
        write_script(cls.scripts_dir, "block", PLATE)
        write_script(cls.scripts_dir, "plate", PLATE)
        cls._saved_root = server.ROOT
        server.ROOT = cls.root
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.url = "http://127.0.0.1:%d/" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=server.watcher, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(
            args=["--use-gl=angle", "--use-angle=swiftshader-webgl"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.ROOT = cls._saved_root
        cls.tmp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.page = self.context.new_page()
        self.page_errors = []
        self.page.on("pageerror", lambda e: self.page_errors.append(str(e)))

    def tearDown(self):
        self.context.close()
        # every test must leave the fixture root with exactly block.py and plate.py
        for name in os.listdir(self.scripts_dir):
            if name not in ("block.py", "plate.py"):
                os.remove(os.path.join(self.scripts_dir, name))

    # -- helpers -------------------------------------------------------------
    def open(self, fragment=""):
        self.page.goto(self.url + fragment)
        self.wait_rendered()

    def wait_rendered(self):
        self.page.wait_for_function("window.__p3d && window.__p3d.lastMeta() !== null", timeout=20000)

    def hook(self, expr):
        return self.page.evaluate("window.__p3d." + expr)

    def click_script(self, name):
        self.page.locator(".item", has_text=name).first.click()

    def row(self, param):
        # :text-is() is an exact match; a substring match would let "D" hit "KIND".
        return self.page.locator('.prow:has(.code:text-is("%s"))' % param)

    def number_input(self, param):
        return self.row(param).locator("input[type=number]")

    # -- smoke ---------------------------------------------------------------
    def test_page_loads_and_renders_first_script(self):
        self.open()
        self.assertEqual(self.page.eval_on_selector_all(".item", "els => els.length"), 2)
        self.assertIn("block()", self.page.text_content("#hud"))
        self.assertEqual(self.hook("lastMeta().solid_count"), 1)
        self.assertEqual(self.page_errors, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: FAIL with a Playwright `TimeoutError` waiting for `window.__p3d`.

- [ ] **Step 4: Add the hook to the viewer**

In `viewer/index.html`, directly after the line `let debounceTimer = null;` add:

```js
let lastMeta = null;       // meta of the last successful render (for overlay redraws and tests)
let renderCount = 0;       // number of /api/render requests issued

// Test hook: read-only access for the Playwright suite. Not used by the UI.
window.__p3d = {
  lastMeta: () => lastMeta,
  userValues: () => userValues,
  renderCount: () => renderCount,
  overlayCount: () => overlay.children.length,
};
```

In the existing `render()` function, change the URL line to increment the counter, and set `lastMeta`:

```js
  renderCount++;
  const url = `/api/render?script=${encodeURIComponent(currentScript)}&params=${encodeURIComponent(JSON.stringify(userValues))}`;
```

and just before `if (rebuildPanel) buildPanel(meta);` add `lastMeta = meta;`.

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 1 test OK (takes a few seconds for Chromium start-up).

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt test_viewer_e2e.py viewer/index.html
git commit -m "Add Playwright end-to-end harness and a viewer test hook"
```

### Task 14: Render pipeline: sequencing, no-flash swap, cached overlays, error clears the panel

**Fixes review items 7, 9 and 12.**

**Files:**
- Modify: `viewer/index.html` (`render`, toolbar toggles)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing tests** (add inside `ViewerE2E`)

```python
    def test_stale_render_response_is_discarded(self):
        self.open()
        real = server.R.render_script

        def slow_for_100(path, params=None, **kw):
            if params and params.get("L") == 100:
                time.sleep(1.5)
            return real(path, params, **kw)

        num = self.number_input("L")
        with mock.patch.object(server.R, "render_script", slow_for_100):
            num.fill("100")
            self.page.wait_for_timeout(300)   # debounce fires -> slow request in flight
            num.fill("200")
            self.page.wait_for_timeout(2500)  # both responses have arrived
        self.assertEqual(self.hook("lastMeta().values.L"), 200)

    def test_overlay_toggles_do_not_rerender_on_the_server(self):
        self.open()
        before = self.hook("renderCount()")
        with_ports = self.hook("overlayCount()")
        self.page.click("#btnPorts")
        self.page.wait_for_timeout(300)
        self.assertEqual(self.hook("renderCount()"), before)
        self.assertLess(self.hook("overlayCount()"), with_ports)
        self.page.click("#btnPorts")
        self.page.wait_for_timeout(300)
        self.assertEqual(self.hook("overlayCount()"), with_ports)
        self.assertEqual(self.hook("renderCount()"), before)

    def test_error_clears_panel_and_hud(self):
        write_script(self.scripts_dir, "broken", BROKEN)
        self.open()
        self.page.wait_for_function("document.querySelectorAll('.item').length === 3", timeout=10000)
        self.click_script("broken.py")
        self.page.wait_for_selector("#banner", state="visible")
        self.assertIn("boom from the script", self.page.text_content("#banner"))
        self.assertEqual(self.page.text_content("#hud").strip(), "—")
        self.assertEqual(self.page.locator(".prow").count(), 0)
        self.assertIn("no render", self.page.text_content("#params"))
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: stale test FAILS (`100 != 200`), toggle test FAILS (`renderCount` grew), error test FAILS (`.prow` count is 2).

- [ ] **Step 3: Replace `render()` and add helpers**

Replace the whole `async function render(...) { ... }` with:

```js
let renderSeq = 0;         // increments per request; responses older than the latest are dropped

function showBanner(text) {
  const banner = document.getElementById('banner');
  banner.style.display = 'block';
  banner.textContent = text;
}
function hideBanner() { document.getElementById('banner').style.display = 'none'; }

function parseGlb(b64) {
  return new Promise((resolve, reject) => loader.parse(b64ToBuf(b64), '', resolve, reject));
}

function showMeta(meta) {
  const unit = (meta.activate && meta.activate.LengthUnit) || 'mm';
  document.getElementById('hud').textContent =
    `${meta.entry}()  ·  ${meta.solid_count} solid(s)  ·  ${meta.ports.length} port(s)  ·  ${unit}`;
  const warns = document.getElementById('warns');
  if (meta.warnings && meta.warnings.length) {
    warns.style.display = 'block';
    warns.textContent = '⚠ ' + meta.warnings.join('\n⚠ ');
  } else warns.style.display = 'none';
}

// Called when a script fails to render: nothing on screen may describe the
// previous script any more, or its sliders would send overrides to this one.
function clearModelUi() {
  clearGroup(modelGroup); clearGroup(overlay);
  lastMeta = null;
  document.getElementById('hud').textContent = '—';
  document.getElementById('warns').style.display = 'none';
  document.getElementById('params').innerHTML = '<div class="empty">no render</div>';
}

async function render({ rebuildPanel = false, frame = false } = {}) {
  if (!currentScript) return;
  const script = currentScript;
  const seq = ++renderSeq;
  renderCount++;
  // Always send only explicit overrides so untouched params follow the file's
  // current defaults (important for live-reload after editing a default).
  const url = `/api/render?script=${encodeURIComponent(script)}&params=${encodeURIComponent(JSON.stringify(userValues))}`;
  let data;
  try {
    data = await api(url);
  } catch (err) {
    if (seq !== renderSeq) return;
    showBanner(String(err.message || err));
    return;
  }
  if (seq !== renderSeq) return;   // a newer request superseded this one; drop the stale response
  if (data.error) {
    showBanner(`⚠ ${script}\n${data.error}`);
    if (rebuildPanel) clearModelUi();
    return;
  }
  const meta = data.meta;
  let gltf = null;
  if (data.glb_b64) {
    try {
      gltf = await parseGlb(data.glb_b64);
    } catch (err) {
      showBanner('GLB load error: ' + err);
      return;
    }
    if (seq !== renderSeq) return;
  }
  hideBanner();
  // Swap only now, so the previous model stays on screen until the new one is ready.
  clearGroup(modelGroup); modelGroup.rotation.y = 0;
  if (gltf) { modelGroup.add(gltf.scene); applyMaterials(); }
  lastMeta = meta;
  if (frame) frameModel(meta.bounds);
  drawOverlays(meta);
  showMeta(meta);
  if (rebuildPanel) buildPanel(meta);
  return meta;
}
```

- [ ] **Step 4: Redraw overlays from cache in the toolbar**

Replace the three toggle lines:

```js
tb('btnPorts', (e) => { showPorts = toggle(e.target); if (lastMeta) drawOverlays(lastMeta); });
tb('btnDims', (e) => { showDims = toggle(e.target); if (lastMeta) drawOverlays(lastMeta); });
tb('btnFixedDims', (e) => { showFixedDims = toggle(e.target); if (lastMeta) drawOverlays(lastMeta); });
```

Also in `loadList`, inside the `if (!scripts.length)` branch, replace the three lines that clear the model, params and hud with a single `clearModelUi();` followed by `list.innerHTML = '<div class="empty">no scripts found</div>'; return;`.

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 4 tests OK.

- [ ] **Step 6: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Drop stale render responses, swap models without flashing, redraw overlays from cache"
```

### Task 15: Script-list events keep your overrides; reconnects and helper edits re-render

**Fixes review item 8 and the SSE reconnect and same-folder helper points.**

**Files:**
- Modify: `viewer/index.html` (`loadList`, `loadScript`, SSE handlers)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_new_script_on_disk_does_not_reset_overrides_or_camera(self):
        self.open()
        self.number_input("L").fill("123")
        self.page.wait_for_function("window.__p3d.lastMeta().values.L === 123", timeout=10000)
        cam_before = self.hook("cameraPosition()")
        write_script(self.scripts_dir, "extra", PLATE)
        self.page.wait_for_function("document.querySelectorAll('.item').length === 3", timeout=10000)
        self.page.wait_for_timeout(500)
        self.assertEqual(self.hook("userValues().L"), 123)
        self.assertEqual(self.number_input("L").input_value(), "123")
        self.assertEqual(self.hook("cameraPosition()"), cam_before)
        self.assertTrue(self.page.locator(".item.sel", has_text="block.py").count() == 1)

    def test_editing_a_sibling_file_rerenders_current_script(self):
        self.open()
        before = self.hook("renderCount()")
        # touch a different file in the same folder (a helper module would be the real case)
        with open(os.path.join(self.scripts_dir, "plate.py"), "a") as f:
            f.write("\n# touched\n")
        self.page.wait_for_function("window.__p3d.renderCount() > %d" % before, timeout=10000)
        self.assertIn("block()", self.page.text_content("#hud"))
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: first FAILS (`userValues().L` is undefined and `cameraPosition` hook missing); second FAILS on timeout (no re-render for a sibling change).

- [ ] **Step 3: Extend the hook and rewrite list loading and SSE**

Add to `window.__p3d`:

```js
  cameraPosition: () => camera.position.toArray().map(v => Math.round(v * 1000) / 1000),
```

Replace `loadScript` and `loadList`:

```js
const dirOf = (p) => p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '';

function markSelected(rel) {
  document.querySelectorAll('.item').forEach(el => el.classList.toggle('sel', el.dataset.path === rel));
}

async function loadScript(rel, initialValues = {}) {
  currentScript = rel;
  currentValues = {};
  userValues = Object.assign({}, initialValues);   // fresh script: start from its own defaults
  markSelected(rel);
  await render({ rebuildPanel: true, frame: true });
}

let listPromise = null;
function loadList(opts) {
  // Coalesce overlapping calls (page open + first SSE message, root switch + __root__ event).
  if (listPromise) return listPromise;
  listPromise = _loadList(opts || {}).finally(() => { listPromise = null; });
  return listPromise;
}

async function _loadList({ preferCurrent = false } = {}) {
  const { root, scripts } = await api('/api/scripts');
  currentRoot = root || '';
  document.getElementById('rootpath').textContent = currentRoot || '—';
  const list = document.getElementById('scriptlist'); list.innerHTML = '';
  if (!scripts.length) {
    currentScript = null;
    clearModelUi();
    list.innerHTML = '<div class="empty">no scripts found</div>';
    return;
  }
  const byDir = {};
  scripts.forEach(s => {
    const d = dirOf(s);
    const f = d ? s.slice(d.length + 1) : s;
    (byDir[d] = byDir[d] || []).push({ f, path: s });
  });
  Object.keys(byDir).sort().forEach(d => {
    const t = document.createElement('div'); t.className = 'group-title'; t.textContent = d || '(root)'; list.appendChild(t);
    byDir[d].forEach(({ f, path }) => {
      const el = document.createElement('div'); el.className = 'item'; el.textContent = f; el.dataset.path = path;
      el.onclick = () => loadScript(path); list.appendChild(el);
    });
  });
  if (preferCurrent && currentScript && scripts.includes(currentScript)) {
    markSelected(currentScript);   // list rebuilt; keep the model, overrides and camera as they are
    return;
  }
  await loadScript(scripts[0]);
}
loadList().catch(err => {
  document.getElementById('scriptlist').innerHTML = '';
  const msg = document.createElement('div'); msg.className = 'empty';
  msg.textContent = 'cannot reach the preview server: ' + (err.message || err);
  document.getElementById('scriptlist').appendChild(msg);
});
```

Replace `connectSSE`:

```js
const dot = document.getElementById('livedot');
let sseWasOpen = false;
function connectSSE() {
  const es = new EventSource('/api/events');
  es.onopen = () => {
    dot.classList.add('live');
    if (sseWasOpen) {
      // Reconnected after the server went away: anything may have changed meanwhile.
      loadList({ preferCurrent: true }).then(() => render({ rebuildPanel: true }));
    }
    sseWasOpen = true;
  };
  es.onerror = () => { dot.classList.remove('live'); };
  es.onmessage = (e) => {
    let d;
    try { d = JSON.parse(e.data); } catch (_) { return; }
    if (!d.changed) return;
    if (d.changed === '__root__' || d.changed === '__scripts__') { loadList({ preferCurrent: true }); return; }
    // Any .py in the current script's folder changed (the script itself or a
    // helper it imports): re-render keeping the user's explicit overrides.
    // Untouched params follow the file's (possibly edited) defaults. Rebuild
    // the panel in case the parameter set changed. Camera is left as-is.
    if (currentScript && dirOf(d.changed) === dirOf(currentScript)) render({ rebuildPanel: true });
  };
}
connectSSE();
```

In `useBrowseFolder`, the three lines `currentScript = null; currentValues = {}; userValues = {};` followed by `await loadList();` stay as they are (a root switch should start fresh).

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 6 tests OK.

- [ ] **Step 5: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Keep overrides and camera across script-list changes; re-render on sibling edits and reconnect"
```

### Task 16: Draw on demand, fix the per-frame resize, parent the key light to the camera, spin a pivot that carries overlays

**Fixes review items 11 and 13 plus the idle GPU and lighting improvements.**

**Files:**
- Modify: `viewer/index.html` (scaffolding, `resize`, `tick`, `frameModel`, `drawOverlays`, `applyMaterials`, toolbar)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_idle_viewer_stops_drawing_and_resizing(self):
        self.open()
        self.page.wait_for_timeout(1500)          # let orbit damping settle
        draws = self.hook("drawCount()"); resizes = self.hook("resizeCount()")
        self.page.wait_for_timeout(1000)
        self.assertEqual(self.hook("drawCount()"), draws)
        self.assertEqual(self.hook("resizeCount()"), resizes)

    def test_hidpi_context_does_not_resize_every_frame(self):
        ctx = self.browser.new_context(viewport={"width": 1000, "height": 700}, device_scale_factor=2)
        try:
            page = ctx.new_page()
            page.goto(self.url)
            page.wait_for_function("window.__p3d && window.__p3d.lastMeta() !== null", timeout=20000)
            page.wait_for_timeout(1500)
            resizes = page.evaluate("window.__p3d.resizeCount()")
            page.wait_for_timeout(1000)
            self.assertEqual(page.evaluate("window.__p3d.resizeCount()"), resizes)
            self.assertLessEqual(resizes, 3)
        finally:
            ctx.close()

    def test_spin_rotates_model_and_overlays_together(self):
        self.open()
        self.assertTrue(self.hook("overlayShareSpinPivot()"))
        self.page.click("#btnSpin")
        self.page.wait_for_timeout(400)
        self.assertGreater(self.hook("pivotRotationY()"), 0)
        self.page.click("#btnSpin")
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: the three new tests FAIL with hook functions undefined.

- [ ] **Step 3: Scaffolding changes**

Replace the lines

```js
scene.add(new THREE.HemisphereLight(0xbfd3ff, 0x28303a, 1.15));
const key = new THREE.DirectionalLight(0xffffff, 2.0); key.position.set(1, 2, 1.5); scene.add(key);
```

with

```js
scene.add(new THREE.HemisphereLight(0xbfd3ff, 0x28303a, 1.15));
// The key light rides with the camera so the side you are looking at is never black.
const key = new THREE.DirectionalLight(0xffffff, 2.0); key.position.set(1, 2, 1.5);
camera.add(key); scene.add(camera);
```

Replace

```js
const modelGroup = new THREE.Group(); scene.add(modelGroup);   // GLB (already Y-up)
const overlay = new THREE.Group(); scene.add(overlay);          // ports + dims
```

with

```js
// Everything that belongs to the part hangs off `pivot`, so Spin turns the
// mesh, the ports and the dimension lines as one.
const pivot = new THREE.Group(); scene.add(pivot);
const modelGroup = new THREE.Group(); pivot.add(modelGroup);   // GLB (already Y-up)
const overlay = new THREE.Group(); pivot.add(overlay);          // ports + dims
```

Replace `resize()` and `tick()`:

```js
let needsDraw = true;      // set by anything that changes what is on screen
let drawCount = 0, resizeCount = 0;
function requestDraw() { needsDraw = true; }

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const cur = renderer.getSize(new THREE.Vector2());   // CSS pixels, unlike canvas.width
  if (cur.x !== w || cur.y !== h) {
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    resizeCount++;
    needsDraw = true;
  }
}
function draw() {
  drawCount++;
  renderer.setViewport(0, 0, canvas.clientWidth, canvas.clientHeight);
  renderer.setScissorTest(false);
  renderer.clear();
  renderer.render(scene, camera);
  renderUcsInset();
}
function tick() {
  resize();
  const moved = controls.update();   // true while orbiting or damping
  if (spin) { pivot.rotation.y += 0.005; needsDraw = true; }
  if (moved || needsDraw) { needsDraw = false; draw(); }
  requestAnimationFrame(tick);
}
tick();
```

- [ ] **Step 4: Request a draw wherever the scene changes**

- End of `frameModel(...)`: add `requestDraw();` as the last statement.
- End of `drawOverlays(...)`: add `requestDraw();` as the last statement.
- End of `applyMaterials()`: add `requestDraw();` after the `traverse` call.
- In `render()`, replace `clearGroup(modelGroup); modelGroup.rotation.y = 0;` with `clearGroup(modelGroup); pivot.rotation.y = 0;`.
- In `clearModelUi()`, add `requestDraw();` as the last statement.
- Toolbar: `tb('btnGrid', (e) => { grid.visible = toggle(e.target); requestDraw(); });` and `tb('btnWire', (e) => { wire = toggle(e.target); applyMaterials(); });` (applyMaterials already requests a draw).

- [ ] **Step 5: Extend the hook**

Add to `window.__p3d`:

```js
  drawCount: () => drawCount,
  resizeCount: () => resizeCount,
  pivotRotationY: () => pivot.rotation.y,
  overlayShareSpinPivot: () => pivot.children.includes(modelGroup) && pivot.children.includes(overlay),
```

- [ ] **Step 6: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 9 tests OK.

- [ ] **Step 7: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Draw on demand, fix HiDPI resize loop, camera-mounted key light, spin overlays with the model"
```

### Task 17: Typed parameter controls and safe text rendering

**Fixes review items 14 and 15 and honours `allow_zero`.**

**Files:**
- Modify: `viewer/index.html` (`buildPanel`)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_metadata_is_rendered_as_text_not_html(self):
        self.open()
        self.assertEqual(self.page.text_content(".meta-line b"), "<b>Plate</b>")
        self.assertEqual(self.page.locator(".meta-line b b").count(), 0)

    def test_enum_and_bool_params_get_typed_controls(self):
        write_script(self.scripts_dir, "enumpart", ENUMPART)
        self.open()
        self.page.wait_for_function("document.querySelectorAll('.item').length === 3", timeout=10000)
        self.click_script("enumpart.py")
        self.page.wait_for_function("window.__p3d.lastMeta().entry === 'enumpart'", timeout=10000)
        kind = self.row("KIND").locator("select")
        self.assertEqual(kind.locator("option").count(), 2)
        kind.select_option("B")
        self.page.wait_for_function("window.__p3d.lastMeta().values.KIND === 'B'", timeout=10000)
        flag = self.row("FLAG").locator("input[type=checkbox]")
        self.assertTrue(flag.is_checked())
        flag.uncheck()
        self.page.wait_for_function("window.__p3d.lastMeta().values.FLAG === false", timeout=10000)
        self.assertEqual(self.row("D").locator("input[type=range]").count(), 1)

    def test_length_slider_cannot_reach_zero(self):
        self.open()
        rng = self.row("L").locator("input[type=range]")
        self.assertGreater(float(rng.get_attribute("min")), 0.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: text test FAILS (`.meta-line b b` count is 1 because the tooltip was injected as HTML); enum test FAILS (no `select`); slider test FAILS (`min` is `0`).

- [ ] **Step 3: Replace `buildPanel`**

```js
function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

function buildPanel(meta) {
  const panel = document.getElementById('params');
  panel.innerHTML = '';
  const act = meta.activate || {};
  const info = el('div', 'meta-line');
  const b = el('b'); b.textContent = act.TooltipShort || meta.entry;
  info.append(b, ` · group “${act.Group || '—'}”`);
  if (act.TooltipLong) {
    info.appendChild(el('br'));
    const t = el('span'); t.style.color = 'var(--muted)'; t.textContent = act.TooltipLong;
    info.appendChild(t);
  }
  panel.appendChild(info);
  currentValues = Object.assign({}, meta.values);
  meta.params.forEach(p => panel.appendChild(buildParamRow(p)));
}

function buildParamRow(p) {
  // effective value: user override if present, otherwise the file's default
  const v = (p.name in userValues) ? userValues[p.name] : p.default;
  currentValues[p.name] = v;
  const row = el('div', 'prow');
  const lbl = el('div', 'lbl');
  const name = el('span', 'name');
  const code = el('span', 'code'); code.textContent = p.name; name.appendChild(code);
  if (p.short && p.short !== p.name) name.append(' · ' + p.short);
  const tt = el('span', 'tt'); tt.textContent = p.type;
  lbl.append(name, tt); row.appendChild(lbl);
  const controls = el('div', 'controls'); row.appendChild(controls);
  const commit = (val) => { currentValues[p.name] = val; userValues[p.name] = val; scheduleRender(); };

  const isBool = p.type === 'BOOL' || p.type === 'BOOLEAN' || p.type === 'b' || typeof v === 'boolean';
  const isText = p.type === 'STRING' || (typeof v === 'string' && isNaN(parseFloat(v)));
  if (p.enum && p.enum.length) {
    const sel = el('select');
    p.enum.forEach(o => {
      const opt = el('option'); opt.value = o; opt.textContent = o;
      if (String(o) === String(v)) opt.selected = true;
      sel.appendChild(opt);
    });
    // Send a number when the option is numeric and the default was numeric; else a string.
    sel.addEventListener('change', () => {
      const s = sel.value;
      commit(typeof p.default === 'number' && s.trim() !== '' && !isNaN(+s) ? +s : s);
    });
    controls.appendChild(sel);
  } else if (isBool) {
    const cb = el('input'); cb.type = 'checkbox'; cb.checked = !!v && v !== '0';
    cb.addEventListener('change', () => commit(cb.checked));
    controls.appendChild(cb);
  } else if (isText) {
    const txt = el('input'); txt.type = 'text'; txt.value = v;
    txt.addEventListener('input', () => commit(txt.value));
    controls.appendChild(txt);
  } else {
    const isInt = p.type === 'INT' || p.type === 'INTEGER';
    const num = parseFloat(v) || 0;
    const sliderMax = Math.max(Math.abs(num) * 3, Math.abs(num) + 50, 10);
    const fineStep = isInt ? 1 : sliderMax / 200;
    // LENGTH (allow_zero false) must not be able to hit 0: that yields empty geometry.
    const sliderMin = p.allow_negative ? -sliderMax : (p.allow_zero ? 0 : fineStep);
    const range = el('input'); range.type = 'range';
    range.min = sliderMin; range.max = sliderMax; range.step = fineStep; range.value = num;
    const nbox = el('input'); nbox.type = 'number'; nbox.step = isInt ? 1 : 'any'; nbox.value = num;
    controls.append(range, nbox);
    const set = (val, from) => {
      let f = parseFloat(val); if (isNaN(f)) return;
      if (isInt) f = Math.round(f);
      if (from !== 'range') { if (f > +range.max) range.max = f; if (f < +range.min) range.min = f; range.value = f; }
      if (from !== 'num') nbox.value = f;
      commit(f);
    };
    range.addEventListener('input', () => set(range.value, 'range'));
    nbox.addEventListener('input', () => set(nbox.value, 'num'));
  }
  if (p.long) { const l = el('div', 'tt'); l.style.marginTop = '4px'; l.textContent = p.long; row.appendChild(l); }
  return row;
}
```

Add CSS for the new controls inside the `/* param panel */` block:

```css
  .prow select, .prow input[type=text] { flex: 1; background: var(--bg); color: var(--fg);
    border: 1px solid var(--line); border-radius: 4px; padding: 3px 5px; font-family: var(--mono); font-size: 12px; }
  .prow input[type=checkbox] { accent-color: var(--accent); width: 16px; height: 16px; }
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 12 tests OK.

- [ ] **Step 5: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Render typed controls for enum, bool and string params; never inject metadata as HTML"
```

### Task 18: Fixed dims draw from `primitive_dims`

The viewer code for this already exists (`drawOverlays` reads `meta.primitive_dims`; `drawDimLine` prefixes the primitive name). Task 8 made the server emit the data. This task only adds the regression test and a label-size tweak.

**Files:**
- Modify: `viewer/index.html` (`drawDimLine`)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_fixed_dims_button_draws_primitive_dimensions(self):
        self.open()
        self.assertEqual(len(self.hook("lastMeta().primitive_dims")), 3)   # BOX: L, W, H
        base = self.hook("overlayCount()")
        self.page.click("#btnFixedDims")
        self.page.wait_for_timeout(200)
        # each dim line adds a line, two end dots and a label = 4 objects
        self.assertEqual(self.hook("overlayCount()"), base + 12)
        self.page.click("#btnFixedDims")
```

- [ ] **Step 2: Run**

Run: `$PY -m unittest test_viewer_e2e.ViewerE2E.test_fixed_dims_button_draws_primitive_dimensions -v`
Expected: PASS already (the data path is complete). If it fails on the count, check `drawDimLine` still adds exactly line + 2 dots + label.

- [ ] **Step 3: Make fixed-dim labels smaller than user dims so they do not compete**

In `drawDimLine`, replace `const lbl = makeLabel(...)` and the two lines after it with:

```js
  const lbl = makeLabel(`${name}=${len.toFixed(1)}`, labelColor);
  if (withPrimitiveName) lbl.scale.multiplyScalar(0.75);
  lbl.position.copy(a.clone().add(b).multiplyScalar(0.5));
  overlay.add(lbl);
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 13 tests OK.

- [ ] **Step 5: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Cover Fixed dims end to end and shrink primitive dimension labels"
```

### Task 19: Script and overrides live in the URL hash

**Files:**
- Modify: `viewer/index.html` (`scheduleRender`, `loadScript`, `_loadList`, `btnReset`)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_hash_restores_script_and_overrides(self):
        self.open("#script=customsupports%2Fplate.py&p=%7B%22L%22%3A77%7D")
        self.page.wait_for_function("window.__p3d.lastMeta().entry === 'plate'", timeout=10000)
        self.assertEqual(self.hook("lastMeta().values.L"), 77)
        self.assertEqual(self.number_input("L").input_value(), "77")

    def test_hash_tracks_changes(self):
        self.open()
        self.number_input("W").fill("33")
        self.page.wait_for_function("location.hash.includes('%22W%22%3A33')", timeout=10000)
        self.assertIn("script=customsupports%2Fblock.py", self.page.evaluate("location.hash"))
        self.page.click("#btnReset")
        self.page.wait_for_function("!location.hash.includes('p=')", timeout=10000)
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: both FAIL (the hash is ignored, and never written).

- [ ] **Step 3: Implement hash state**

Add after the `window.__p3d` definition:

```js
// ---- URL hash state: #script=REL&p={"D":300} ---------------------------------
function readHash() {
  try {
    const h = new URLSearchParams(location.hash.slice(1));
    const values = h.get('p') ? JSON.parse(h.get('p')) : {};
    return { script: h.get('script') || null, values: (values && typeof values === 'object') ? values : {} };
  } catch (_) { return { script: null, values: {} }; }
}
function writeHash() {
  const h = new URLSearchParams();
  if (currentScript) h.set('script', currentScript);
  if (Object.keys(userValues).length) h.set('p', JSON.stringify(userValues));
  history.replaceState(null, '', h.toString() ? '#' + h.toString() : location.pathname);
}
let startupHash = readHash();   // consumed by the first list load only
```

In `scheduleRender()` add `writeHash();` as the first statement. In `loadScript()` add `writeHash();` right after `markSelected(rel);`.

In `_loadList`, replace the final `await loadScript(scripts[0]);` with:

```js
  const wanted = startupHash.script && scripts.includes(startupHash.script) ? startupHash.script : scripts[0];
  const initial = startupHash.values;
  startupHash = { script: null, values: {} };
  await loadScript(wanted, initial);
```

Replace the reset button handler:

```js
tb('btnReset', () => { userValues = {}; writeHash(); render({ rebuildPanel: true, frame: true }); });
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 15 tests OK.

- [ ] **Step 5: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Keep the current script and parameter overrides in the URL hash"
```

### Task 20: Render time in the HUD, highlighted traceback, Export GLB and Copy params buttons

**Files:**
- Modify: `viewer/index.html` (toolbar markup, `showMeta`, `showBanner`, toolbar handlers, CSS)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_hud_shows_render_time(self):
        self.open()
        self.assertRegex(self.page.text_content("#hud"), r"\d+(\.\d+)? ms")

    def test_traceback_lines_from_the_script_are_highlighted(self):
        write_script(self.scripts_dir, "broken", BROKEN)
        self.open()
        self.page.wait_for_function("document.querySelectorAll('.item').length === 3", timeout=10000)
        self.click_script("broken.py")
        self.page.wait_for_selector("#banner .hl", state="visible", timeout=10000)
        self.assertIn("broken.py", self.page.text_content("#banner .hl"))

    def test_param_string_and_export_are_available(self):
        self.open()
        self.number_input("L").fill("88")
        self.page.wait_for_function("window.__p3d.lastMeta().values.L === 88", timeout=10000)
        self.assertEqual(self.hook("paramString()"), "render.py customsupports/block.py -p L=88")
        self.assertEqual(self.hook("exportName()"), "block.glb")
        self.assertFalse(self.page.locator("#btnExport").is_disabled())
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: all three FAIL (no "ms" in HUD, no `.hl`, hook functions missing).

- [ ] **Step 3: Toolbar markup**

After `<button class="btn" id="btnSpin">Spin</button>` add:

```html
        <button class="btn" id="btnExport" title="Download the current mesh as .glb">Export GLB</button>
        <button class="btn" id="btnCopy" title="Copy a render.py command line with your overrides">Copy params</button>
```

Add CSS after the `#banner { ... }` rule:

```css
  #banner .hl { background: rgba(255,107,107,.22); color: #fff; }
```

- [ ] **Step 4: HUD, banner, export, copy**

In `showMeta`, replace the HUD line:

```js
  const ms = typeof meta.elapsed_ms === 'number' ? `  ·  ${meta.elapsed_ms} ms` : '';
  document.getElementById('hud').textContent =
    `${meta.entry}()  ·  ${meta.solid_count} solid(s)  ·  ${meta.ports.length} port(s)  ·  ${unit}${ms}`;
```

Replace `showBanner`:

```js
function showBanner(text) {
  const banner = document.getElementById('banner');
  banner.style.display = 'block';
  banner.textContent = '';
  // Highlight traceback lines that point into the current script so the
  // offending line stands out from the shim frames.
  const stem = currentScript ? currentScript.slice(currentScript.lastIndexOf('/') + 1) : null;
  String(text).split('\n').forEach((line, i) => {
    const span = document.createElement('span');
    span.textContent = (i ? '\n' : '') + line;
    if (stem && line.includes('File "') && line.includes(stem)) span.className = 'hl';
    banner.appendChild(span);
  });
}
```

Add these helpers after `clearModelUi`:

```js
let lastGlbB64 = null;    // kept for Export GLB

function exportName() {
  if (!currentScript) return 'model.glb';
  const stem = currentScript.slice(currentScript.lastIndexOf('/') + 1).replace(/\.py$/, '');
  return stem + '.glb';
}
function paramString() {
  if (!currentScript) return '';
  const parts = Object.entries(userValues).map(([k, v]) => `${k}=${typeof v === 'string' ? JSON.stringify(v) : v}`);
  return `render.py ${currentScript}` + (parts.length ? ' -p ' + parts.join(' ') : '');
}
function downloadGlb() {
  if (!lastGlbB64) return;
  const blob = new Blob([b64ToBuf(lastGlbB64)], { type: 'model/gltf-binary' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = exportName();
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
async function copyParams() {
  const s = paramString();
  try { await navigator.clipboard.writeText(s); }
  catch (_) { window.prompt('Copy this command line:', s); }
}
```

In `render()`, after `lastMeta = meta;` add `lastGlbB64 = data.glb_b64 || null; document.getElementById('btnExport').disabled = !lastGlbB64;`. In `clearModelUi()` add `lastGlbB64 = null; document.getElementById('btnExport').disabled = true;`.

Toolbar handlers:

```js
tb('btnExport', () => downloadGlb());
tb('btnCopy', () => copyParams());
```

Add to `window.__p3d`: `paramString, exportName,`.

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 18 tests OK.

- [ ] **Step 6: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Show render time, highlight script traceback lines, add Export GLB and Copy params"
```

### Task 21: Facet count selector

**Files:**
- Modify: `viewer/index.html` (toolbar, `render` URL, handler)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_segments_select_changes_mesh_density(self):
        self.open()
        self.assertEqual(self.hook("lastMeta().segments"), server.R.Scene().segments)
        self.page.select_option("#segSel", "32")
        self.page.wait_for_function("window.__p3d.lastMeta().segments === 32", timeout=10000)
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e.ViewerE2E.test_segments_select_changes_mesh_density -v`
Expected: FAIL, no element `#segSel`.

- [ ] **Step 3: Implement**

Toolbar markup, after the Copy params button:

```html
        <select class="btn" id="segSel" title="Facets per circle (preview smoothness vs speed)">
          <option value="32">32 facets</option>
          <option value="48">48 facets</option>
          <option value="96" selected>96 facets</option>
          <option value="160">160 facets</option>
        </select>
```

After `let renderSeq = 0;` add `let segments = 96;`. In `render()` change the URL to append `&segments=${segments}`:

```js
  const url = `/api/render?script=${encodeURIComponent(script)}&params=${encodeURIComponent(JSON.stringify(userValues))}&segments=${segments}`;
```

Handler:

```js
document.getElementById('segSel').addEventListener('change', (e) => { segments = +e.target.value; render(); });
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 19 tests OK.

- [ ] **Step 5: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Add a facet count selector to the toolbar"
```

### Task 22: Section cut

**Files:**
- Modify: `viewer/index.html` (toolbar, scaffolding, `applyMaterials`, handlers, CSS)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_section_cut_clips_materials(self):
        self.open()
        self.assertEqual(self.hook("clipPlaneCount()"), 0)
        self.page.click("#btnSection")
        self.page.wait_for_timeout(200)
        self.assertGreater(self.hook("clipPlaneCount()"), 0)
        self.page.click("#btnSecAxis")
        self.assertEqual(self.page.text_content("#btnSecAxis").strip(), "Axis Y")
        self.page.click("#btnSection")
        self.page.wait_for_timeout(200)
        self.assertEqual(self.hook("clipPlaneCount()"), 0)
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e.ViewerE2E.test_section_cut_clips_materials -v`
Expected: FAIL, hook `clipPlaneCount` missing.

- [ ] **Step 3: Implement**

Toolbar markup after the segments select:

```html
        <button class="btn" id="btnSection" title="Cut the model with a plane">Section</button>
        <button class="btn" id="btnSecAxis" hidden title="Which Plant axis the cut plane is normal to">Axis Z</button>
        <input type="range" id="secPos" min="0" max="100" value="50" hidden title="Cut position">
```

CSS:

```css
  #toolbar input[type=range] { width: 120px; accent-color: var(--accent); align-self: center; }
```

Scaffolding, after `renderer.autoClear = false;`:

```js
renderer.localClippingEnabled = true;
```

Add after `drawOverlays`:

```js
// ---- section cut ------------------------------------------------------------
// Viewer axes vs Plant axes: viewer X = Plant X, viewer Y = Plant Z, viewer Z = Plant -Y.
const SECTION_AXES = [{ viewer: 0, label: 'X' }, { viewer: 1, label: 'Z' }, { viewer: 2, label: 'Y' }];
let sectionOn = false, sectionAxisIdx = 1, sectionFrac = 0.5;
const sectionPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);

function updateSection() {
  const box = new THREE.Box3().setFromObject(modelGroup);
  if (!box.isEmpty()) {
    const axis = SECTION_AXES[sectionAxisIdx].viewer;
    const lo = box.min.getComponent(axis), hi = box.max.getComponent(axis);
    const pos = lo + (hi - lo) * sectionFrac;
    const n = new THREE.Vector3(); n.setComponent(axis, -1);
    // Plane: n·p + c = 0. three.js keeps the side where n·p + c >= 0,
    // i.e. coordinate <= pos. The cut opens the interior towards the camera.
    sectionPlane.set(n, pos);
  }
  const planes = sectionOn ? [sectionPlane] : [];
  modelGroup.traverse(o => {
    const mats = o.material ? [].concat(o.material) : [];
    mats.forEach(m => { m.clippingPlanes = planes; m.needsUpdate = true; });
  });
  document.getElementById('btnSecAxis').hidden = !sectionOn;
  document.getElementById('secPos').hidden = !sectionOn;
  document.getElementById('btnSecAxis').textContent = 'Axis ' + SECTION_AXES[sectionAxisIdx].label;
  requestDraw();
}
```

At the end of `applyMaterials()`, before `requestDraw();`, add `updateSection();` so a freshly loaded model inherits the cut.

Handlers:

```js
tb('btnSection', (e) => { sectionOn = toggle(e.target); updateSection(); });
tb('btnSecAxis', () => { sectionAxisIdx = (sectionAxisIdx + 1) % SECTION_AXES.length; updateSection(); });
document.getElementById('secPos').addEventListener('input', (e) => { sectionFrac = e.target.value / 100; updateSection(); });
```

Hook:

```js
  clipPlaneCount: () => { let n = 0; modelGroup.traverse(o => { if (o.isMesh) n += (o.material.clippingPlanes || []).length; }); return n; },
```

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 20 tests OK.

- [ ] **Step 5: Manual check**

Run: `$PY server.py --root <a folder with real scripts>`. Turn Section on, drag the slider, cycle the axis. The interior should show because materials are double-sided. Spin while sectioned: the plane stays fixed in the world while the model turns, which is expected.

- [ ] **Step 6: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Add a section cut with axis and position controls"
```

### Task 23: Measure tool

**Files:**
- Modify: `viewer/index.html` (toolbar, measure group, pointer handlers, `render`)
- Test: `test_viewer_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_measure_two_clicks_reports_distance(self):
        self.open()
        self.page.click("#btnMeasure")
        box = self.page.locator("#canvas").bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.click(cx - 15, cy)
        self.page.mouse.click(cx + 15, cy)
        self.page.wait_for_function("window.__p3d.measureCount() === 2", timeout=5000)
        self.assertGreater(self.hook("measureDistance()"), 0)
        self.assertIn("Δ=", self.page.text_content("#hud"))
        self.page.click("#btnMeasure")
        self.assertEqual(self.hook("measureCount()"), 0)
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_viewer_e2e.ViewerE2E.test_measure_two_clicks_reports_distance -v`
Expected: FAIL, no `#btnMeasure`.

- [ ] **Step 3: Implement**

Toolbar markup after the section slider:

```html
        <button class="btn" id="btnMeasure" title="Click two points on the model to measure">Measure</button>
```

Scaffolding: after `const overlay = new THREE.Group(); pivot.add(overlay);` add:

```js
const measureGroup = new THREE.Group(); pivot.add(measureGroup);   // measure tool marks
```

Add after the section-cut block:

```js
// ---- measure tool -------------------------------------------------------------
let measureOn = false, measurePts = [];
const raycaster = new THREE.Raycaster();
let pointerDownAt = null;

function measureDistance() {
  return measurePts.length === 2 ? measurePts[0].distanceTo(measurePts[1]) : 0;
}

function drawMeasure() {
  clearGroup(measureGroup);
  const color = 0xff7ad9;
  measurePts.forEach(p => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(modelRadius * 0.015, 12, 12),
      new THREE.MeshBasicMaterial({ color, depthTest: false }));
    m.position.copy(p); m.renderOrder = 998; measureGroup.add(m);
  });
  if (measurePts.length === 2) {
    const g = new THREE.BufferGeometry().setFromPoints(measurePts);
    const line = new THREE.Line(g, new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.95 }));
    line.renderOrder = 998; measureGroup.add(line);
    const unit = (lastMeta && lastMeta.activate && lastMeta.activate.LengthUnit) || 'mm';
    const lbl = makeLabel(`Δ=${measureDistance().toFixed(1)} ${unit}`, '#ffb3ec');
    lbl.position.copy(measurePts[0].clone().add(measurePts[1]).multiplyScalar(0.5));
    measureGroup.add(lbl);
    if (lastMeta) showMeta(lastMeta);
  }
  requestDraw();
}

function pickOnModel(clientX, clientY) {
  const r = canvas.getBoundingClientRect();
  const ndc = new THREE.Vector2(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const meshes = []; modelGroup.traverse(o => { if (o.isMesh) meshes.push(o); });
  const hit = raycaster.intersectObjects(meshes, false)[0];
  return hit ? pivot.worldToLocal(hit.point.clone()) : null;   // store in pivot space so Spin carries it
}

canvas.addEventListener('pointerdown', (e) => { pointerDownAt = [e.clientX, e.clientY]; });
canvas.addEventListener('pointerup', (e) => {
  if (!measureOn || !pointerDownAt) return;
  const moved = Math.hypot(e.clientX - pointerDownAt[0], e.clientY - pointerDownAt[1]);
  pointerDownAt = null;
  if (moved > 4) return;             // that was an orbit drag, not a click
  const p = pickOnModel(e.clientX, e.clientY);
  if (!p) return;
  if (measurePts.length >= 2) measurePts = [];
  measurePts.push(p);
  drawMeasure();
});
```

In `showMeta`, extend the HUD text so a live measurement is appended:

```js
  const meas = measurePts.length === 2 ? `  ·  Δ=${measureDistance().toFixed(1)} ${unit}` : '';
  document.getElementById('hud').textContent =
    `${meta.entry}()  ·  ${meta.solid_count} solid(s)  ·  ${meta.ports.length} port(s)  ·  ${unit}${ms}${meas}`;
```

In `render()`, right after `clearGroup(modelGroup); pivot.rotation.y = 0;` add `measurePts = []; clearGroup(measureGroup);` (a new mesh invalidates old picks). In `clearModelUi()` add the same two statements.

Handler:

```js
tb('btnMeasure', (e) => { measureOn = toggle(e.target); measurePts = []; drawMeasure(); canvas.style.cursor = measureOn ? 'crosshair' : ''; });
```

Hook: `measureCount: () => measurePts.length, measureDistance,`.

- [ ] **Step 4: Run to verify pass**

Run: `$PY -m unittest test_viewer_e2e -v`
Expected: 21 tests OK.

- [ ] **Step 5: Commit**

```bash
git add viewer/index.html test_viewer_e2e.py
git commit -m "Add a two-click measure tool"
```

---

## Phase 5: Packaging, docs, coverage, CI

### Task 24: Launchers that work on Windows

**Files:**
- Modify: `p3dpreview`
- Create: `p3dpreview.ps1`
- Modify: `shot.py` (cross-platform default output)

- [ ] **Step 1: Rewrite `p3dpreview`**

```bash
#!/usr/bin/env bash
# p3dpreview - launch the Plant 3D live preview server.
#
# Creates/uses a local venv, installs deps on first run, then serves the viewer
# and opens a browser. Edit any script under the chosen root and save to see it
# re-render live.
#
#   ./p3dpreview --root /path/to/your/plant3d/scripts
#   ./p3dpreview --port 9000 --no-open
#
# Works from Linux/macOS shells and from Git Bash on Windows. PowerShell users:
# .\p3dpreview.ps1
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) PY="$VENV/Scripts/python.exe"; SYSPY="python" ;;
  *)                    PY="$VENV/bin/python";          SYSPY="python3" ;;
esac

if [ ! -x "$PY" ]; then
  echo "[p3dpreview] creating venv..."
  "$SYSPY" -m venv "$VENV"
fi

# Install deps if the CAD kernel isn't importable yet.
if ! "$PY" -c "import manifold3d, trimesh, scipy" >/dev/null 2>&1; then
  echo "[p3dpreview] installing dependencies (first run)..."
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r "$HERE/requirements.txt"
fi

exec "$PY" "$HERE/server.py" "$@"
```

- [ ] **Step 2: Create `p3dpreview.ps1`**

```powershell
# p3dpreview.ps1 - launch the Plant 3D live preview server from PowerShell.
#   .\p3dpreview.ps1 --root C:\path\to\your\plant3d\scripts
#   .\p3dpreview.ps1 --port 9000 --no-open
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Here ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "[p3dpreview] creating venv..."
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { & py -3 -m venv $Venv } else { & python -m venv $Venv }
}

& $Py -c "import manifold3d, trimesh, scipy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[p3dpreview] installing dependencies (first run)..."
    & $Py -m pip install --quiet --upgrade pip
    & $Py -m pip install --quiet -r (Join-Path $Here "requirements.txt")
}

& $Py (Join-Path $Here "server.py") @args
```

- [ ] **Step 3: Make `shot.py` defaults cross-platform**

Replace the `OUT` line:

```python
OUT = sys.argv[2] if len(sys.argv) > 2 else "pw_shot.png"   # written to the current directory
```

- [ ] **Step 4: Verify both launchers start and stop cleanly**

Git Bash: `./p3dpreview --no-open --port 8771 --root .` then Ctrl-C.
Expected: `Plant 3D preview server running at http://127.0.0.1:8771/` then `bye`.

PowerShell: `.\p3dpreview.ps1 --no-open --port 8771 --root .` then Ctrl-C.
Expected: the same two lines.

Port clash check while one is running: start a second on the same port.
Expected on Linux: `Cannot listen on 127.0.0.1:8771 (...). Is another preview server running? Try --port with a different number.` and exit code 1.
On Windows the second bind may be allowed by the OS because `HTTPServer` sets `SO_REUSEADDR` [Uncertain]; if the second instance starts instead of erroring, that is the socket layer, not this code. The unit test in Task 12 covers the error path deterministically.

- [ ] **Step 5: Commit**

```bash
git add p3dpreview p3dpreview.ps1 shot.py
git commit -m "Make the launcher work on Windows and add a PowerShell launcher"
```

### Task 25: CLI writes `<stem>.meta.json`; gitignore; third-party notice; LICENSE placeholder

**Files:**
- Modify: `render.py` (`main`)
- Modify: `.gitignore`
- Create: `vendor/THIRD_PARTY.md`
- Test: `test_shim.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_cli_writes_glb_and_meta_json_next_to_script(self):
        import subprocess
        import tempfile
        from testutil import write_script
        with tempfile.TemporaryDirectory() as td:
            path = write_script(td, "clipart", """
                from varmain.primitiv import *
                from varmain.custom import *

                @activate(Group="Test", LengthUnit="mm")
                @param(D=LENGTH, TooltipShort="Diameter")
                def {stem}(s, D=20.0, **kw):
                    SPHERE(s, R=D / 2.0)
                """)
            here = os.path.dirname(os.path.abspath(__file__))
            proc = subprocess.run([sys.executable, os.path.join(here, "render.py"), path, "-p", "D=40"],
                                  capture_output=True, text=True, cwd=here)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.exists(os.path.join(td, "clipart.glb")))
            meta_path = os.path.join(td, "clipart.meta.json")
            self.assertTrue(os.path.exists(meta_path))
            import json
            with open(meta_path) as f:
                self.assertEqual(json.load(f)["values"]["D"], 40.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m unittest test_shim.ShimTests.test_cli_writes_glb_and_meta_json_next_to_script -v`
Expected: FAIL, `clipart.meta.json` does not exist (the CLI writes `clipart.json`).

- [ ] **Step 3: Update `main` in `render.py`**

Replace the JSON write:

```python
    meta_path = base + ".meta.json"
    with open(meta_path, "w") as f:
        json.dump(result["meta"], f, indent=2)
    print("wrote", meta_path)
```

and update the module docstring line to `# -> script.glb + script.meta.json`.

- [ ] **Step 4: Housekeeping files**

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
*.glb
*.meta.json
pw_shot.png
```

`vendor/THIRD_PARTY.md`:

```markdown
# Third-party code in this folder

- `three.module.js`, `controls/OrbitControls.js`, `loaders/GLTFLoader.js`,
  `utils/BufferGeometryUtils.js`: three.js, revision r160.
  Copyright 2010-2023 Three.js Authors. Licensed under the MIT License
  (SPDX-License-Identifier: MIT), as stated in the file header of
  `three.module.js`. Source: https://github.com/mrdoob/three.js
```

LICENSE for this repository: the licence is the owner's choice and is not decided by this plan. Do **not** create a `LICENSE` file until the owner names one. Record the open decision in the README "Licence" section (Task 27) as `[TO CONFIRM]`.

- [ ] **Step 5: Run to verify pass**

Run: `$PY -m unittest -v`
Expected: all tests OK (43 non-e2e plus 21 e2e).

- [ ] **Step 6: Commit**

```bash
git add render.py .gitignore vendor/THIRD_PARTY.md test_shim.py
git commit -m "Write CLI metadata as .meta.json, ignore generated files, add third-party notice"
```

### Task 26: Kernel coverage tests and no more vacuous pass

**Files:**
- Create: `test_kernel_primitives.py`
- Modify: `test_render_semantics.py` (`test_rectangular_supports_use_plant_box_axes`)

- [ ] **Step 1: Write `test_kernel_primitives.py`**

Tolerances: a 96-facet polygon has 99.93 percent of the circle's area, so 1 percent covers cylinders, cones and tori; sphere tessellation is coarser, so 2 percent there.

```python
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from testutil import render_temp_script, glb_volume  # noqa: E402

HEADER = """
    from varmain.primitiv import *
    from varmain.custom import *

    @activate(Group="Test", LengthUnit="mm")
    def {stem}(s, **kw):
    """


def _script(body):
    return HEADER + "\n".join("        " + line for line in body.strip().splitlines()) + "\n"


class PrimitiveVolumeTests(unittest.TestCase):
    def assertVolume(self, stem, body, expected, rel=0.01):
        result = render_temp_script(stem, _script(body))
        self.assertEqual(result["meta"]["warnings"], [])
        vol = glb_volume(result)
        self.assertAlmostEqual(vol / expected, 1.0, delta=rel,
                               msg="volume %.3f vs expected %.3f" % (vol, expected))
        return result

    def test_hollow_cylinder(self):
        self.assertVolume("hollow", "CYLINDER(s, R=10.0, H=20.0, O=4.0)",
                          math.pi * (10.0 ** 2 - 4.0 ** 2) * 20.0)

    def test_tapered_cylinder_matches_frustum(self):
        r1, r2, h = 10.0, 5.0, 12.0
        self.assertVolume("taper", "CYLINDER(s, R1=10.0, R2=5.0, H=12.0)",
                          math.pi * h * (r1 ** 2 + r1 * r2 + r2 ** 2) / 3.0)

    def test_cone(self):
        r1, r2, h = 10.0, 2.0, 15.0
        result = self.assertVolume("cone", "CONE(s, R1=10.0, R2=2.0, H=15.0)",
                                   math.pi * h * (r1 ** 2 + r1 * r2 + r2 ** 2) / 3.0)
        b = result["meta"]["bounds"]
        # base on Plant Z=0, apex at Z=H; Plant Z maps to viewer Y
        self.assertAlmostEqual(b["min"][1], 0.0, places=4)
        self.assertAlmostEqual(b["max"][1], 15.0, places=4)

    def test_torus(self):
        r1, r2 = 30.0, 4.0
        result = self.assertVolume("torus", "TORUS(s, R1=30.0, R2=4.0)", 2 * math.pi ** 2 * r1 * r2 ** 2)
        b = result["meta"]["bounds"]
        self.assertAlmostEqual(b["max"][0], 34.0, places=3)   # ring in Plant XY plane
        self.assertAlmostEqual(b["max"][1], 4.0, places=3)    # tube radius along Plant Z

    def test_sphere(self):
        self.assertVolume("sphere", "SPHERE(s, R=7.0)", 4.0 / 3.0 * math.pi * 7.0 ** 3, rel=0.02)

    def test_halfsphere_keeps_positive_z(self):
        result = self.assertVolume("half", "HALFSPHERE(s, R=7.0)", 2.0 / 3.0 * math.pi * 7.0 ** 3, rel=0.02)
        b = result["meta"]["bounds"]
        self.assertAlmostEqual(b["min"][1], 0.0, places=3)
        self.assertAlmostEqual(b["max"][1], 7.0, places=3)

    def test_ellipsoidhead_is_half_sphere_squashed_to_h(self):
        r, h = 10.0, 4.0
        result = self.assertVolume("head", "ELLIPSOIDHEAD(s, R=10.0, H=4.0)", 2.0 / 3.0 * math.pi * r ** 2 * h, rel=0.02)
        self.assertAlmostEqual(result["meta"]["bounds"]["max"][1], 4.0, places=3)

    def test_intersect_with_keeps_common_volume(self):
        result = self.assertVolume("inter", """
            a = BOX(s, L=10.0, W=10.0, H=10.0)
            b = BOX(s, L=10.0, W=10.0, H=10.0).translate((5.0, 0.0, 0.0))
            a.intersectWith(b)
            """, 5.0 * 10.0 * 10.0)
        self.assertEqual(result["meta"]["solid_count"], 1)

    def test_scale_scalar_and_vector(self):
        self.assertVolume("scale1", "BOX(s, L=10.0, W=10.0, H=10.0).scale(2.0)", 8000.0)
        result = self.assertVolume("scale3", "BOX(s, L=10.0, W=10.0, H=10.0).scale((1.0, 2.0, 3.0))", 6000.0)
        b = result["meta"]["bounds"]
        self.assertAlmostEqual(b["max"][0] - b["min"][0], 10.0, places=4)   # H along X, unscaled
        self.assertAlmostEqual(b["max"][1] - b["min"][1], 30.0, places=4)   # W along Plant Z -> viewer Y, x3
        self.assertAlmostEqual(b["max"][2] - b["min"][2], 20.0, places=4)   # L along Plant Y -> viewer Z, x2


class SafePathTests(unittest.TestCase):
    def test_safe_script_path_rejects_escape_and_non_scripts(self):
        import tempfile
        import server
        saved = server.ROOT
        try:
            with tempfile.TemporaryDirectory() as td:
                server.ROOT = os.path.abspath(td)
                open(os.path.join(td, "ok.py"), "w").close()
                open(os.path.join(td, "notes.txt"), "w").close()
                self.assertEqual(server._safe_script_path("ok.py"), os.path.join(server.ROOT, "ok.py"))
                self.assertEqual(server._safe_script_path("\\ok.py"), os.path.join(server.ROOT, "ok.py"))
                with self.assertRaises(ValueError):
                    server._safe_script_path("../server.py")
                with self.assertRaises(ValueError):
                    server._safe_script_path("notes.txt")
                with self.assertRaises(ValueError):
                    server._safe_script_path("missing.py")
        finally:
            server.ROOT = saved


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run**

Run: `$PY -m unittest test_kernel_primitives -v`
Expected: 11 tests OK. If a volume test fails by a small margin, report the measured ratio rather than loosening the tolerance without understanding why.

- [ ] **Step 3: Make the parent-repo test skip visibly**

In `test_render_semantics.py`, replace the body of `test_rectangular_supports_use_plant_box_axes` up to the `for rel in` loop so that missing fixtures skip:

```python
    def test_rectangular_supports_use_plant_box_axes(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        candidates = (
            "customsupports/supportpost.py",
            "customsupports/supportaframe.py",
            "customsupports/teepost.py",
        )
        present = [rel for rel in candidates if os.path.exists(os.path.join(repo_root, rel))]
        if not present:
            self.skipTest("no Plant 3D repo scripts found next to this checkout")
        for rel in present:
            with self.subTest(script=rel):
                result = render_script(os.path.join(repo_root, rel))
                meta = result["meta"]

                self.assertEqual(meta["solid_count"], 1)
                self.assertEqual(meta["warnings"], [])
                self.assertEqual(self.mesh_island_count(result), 1)
```

- [ ] **Step 4: Run everything**

Run: `$PY -m unittest -v`
Expected: all OK, with `test_rectangular_supports_use_plant_box_axes ... skipped 'no Plant 3D repo scripts found next to this checkout'` on this machine.

- [ ] **Step 5: Commit**

```bash
git add test_kernel_primitives.py test_render_semantics.py
git commit -m "Cover every primitive, intersectWith, scale and path safety; skip instead of passing vacuously"
```

### Task 27: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md`**

```markdown
# Plant 3D Live Preview

A browser-based live renderer for Plant 3D custom Python parts. Point it at a
folder of scripts, edit a `.py`, hit **save**, and the 3D model re-renders in
the browser.

![Plant 3D Live Preview demo](demo.gif)

## Usage

```bash
./p3dpreview --root /path/to/your/plant3d/scripts     # Linux, macOS, Git Bash
.\p3dpreview.ps1 --root C:\path\to\your\plant3d\scripts  # PowerShell
# first run creates a venv + installs deps, then opens the browser
```

The root can be any folder. Every `.py` directly inside it, or one folder
down (for example `customfittings/` and `customsupports/`), is listed.

Then:

- **Left panel** — click any script to load it. New or deleted `.py` files appear
  automatically. **Browse** lets you switch root without restarting.
- **Middle** — orbit (drag), zoom (wheel), pan (right-drag). Toolbar: **Frame**
  recentres; **Reset params** clears your overrides; **Grid**, **Ports** (blue),
  **Dims** (orange, from `setLinearDimension`), **Fixed dims** (green, each
  primitive's own radii and lengths), **Wireframe**, **Spin**; **Export GLB**
  downloads the mesh; **Copy params** puts a `render.py ... -p` command line on
  the clipboard; the facet selector trades smoothness for speed; **Section**
  cuts the model with a plane you can slide along X, Y or Z; **Measure** reports
  the distance between two clicked points.
- **Right panel** — every `@param` becomes a control built from the script's
  own metadata: sliders for lengths and angles, a dropdown for `@enum` values,
  a checkbox for booleans, a text box for strings.
- **Live reload** — the green dot means the file watcher is connected. Save the
  current script, or any helper module in the same folder, and it re-renders.
  Untouched params follow the file's (possibly edited) defaults; params you've
  changed keep your value. The current script and your overrides are kept in the
  URL, so a refresh or a shared link restores them.
- **Errors** — a script that raises shows the traceback in a red banner, with
  the lines from your script highlighted. Zero or negative sizes, and primitives
  the preview does not model, produce a warning instead of silently vanishing.

## Coverage

Modelled primitives: `BOX`, `CYLINDER` (incl. hollow via `O=`, and tapered
`R1/R2`), `CONE`, `TORUS`, `SPHERE`, `HALFSPHERE`, `ELLIPSOIDHEAD`. Transforms
(`translate`, `rotateX/Y/Z`, `scale`), booleans (`uniteWith`, `subtractFrom`,
`intersectWith`), `erase`, `setPoint`, `setLinearDimension`, and `aqa.math`
(everything in Python's `math` plus `asRadiants`) are supported. Other Plant
primitives draw a labelled placeholder cube and a warning so a script never
hard-crashes on an unmodelled call.

## Options

```bash
./p3dpreview --port 9000 --no-open
./p3dpreview --host 0.0.0.0                    # expose on the LAN (see Security)
./p3dpreview --host 0.0.0.0 --allow-remote-root
```

### One-off render from the CLI (no browser)

```bash
.venv/bin/python render.py /path/to/scripts/customsupports/yourpart.py -p D=300 L=200
# Windows: .venv\Scripts\python.exe render.py ...
# -> yourpart.glb + yourpart.meta.json (params schema, ports, dims, warnings, bounds)
```

## Security

The server executes the Python scripts under the chosen root. On the default
loopback bind only your own machine can reach it. With `--host 0.0.0.0` anyone
on the network can render any script under the root; folder browsing and root
switching are disabled in that mode unless you pass `--allow-remote-root`.
There is no authentication. Do not expose it beyond a trusted network.

## Development

```bash
$PY -m pip install -r requirements-dev.txt
$PY -m playwright install chromium        # once, for the end-to-end tests
$PY -m unittest -v                        # unit + HTTP + end-to-end tests
```

End-to-end tests are skipped automatically when Playwright is not installed.

## Caveats

- This is a **mesh** preview (fast, robust booleans), not a B-rep. Geometry,
  proportions, ports and dimensions are faithful; it is not a manufacturing model.
- `CONE`'s `E=` (eccentricity) is treated as 0.
- Coordinate mapping: Plant is Z-up; the viewer is Y-up. The GLB and all overlay
  points are transformed consistently, so ports/dimensions line up with the mesh.
- The exact surface of Plant's `aqa.math` and the syntax of `@enum` have not
  been confirmed against Autodesk documentation [TO CONFIRM].

## Licence

[TO CONFIRM] — the repository licence has not been chosen yet. Vendored
third-party code is listed in `vendor/THIRD_PARTY.md`.
```

- [ ] **Step 2: Check every claim in the README against the code**

Walk each bullet: the button names must match `viewer/index.html` `id`/labels; the flags must match `server.py` `argparse`; the CLI output names must match `render.py`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Rewrite README for any-folder roots, new toolbar features, security and development"
```

### Task 28: Continuous integration

**Files:**
- Create: `.github/workflows/test.yml`

The repository remote is `https://github.com/ajcraig99/plant3d-live-preview.git`, so GitHub Actions applies. Action version tags below are the ones in common use at the time of writing; confirm the current major versions on the GitHub Marketplace before merging [TO CONFIRM].

- [ ] **Step 1: Write the workflow**

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements-dev.txt
      - name: Install Chromium for Playwright
        run: python -m playwright install --with-deps chromium
      - name: Run tests
        run: python -m unittest -v
```

- [ ] **Step 2: Push the branch and watch the run**

```bash
git add .github/workflows/test.yml
git commit -m "Run the test suite on Ubuntu and Windows in GitHub Actions"
git push -u origin review-fixes
gh run watch
```

Expected: both matrix legs green. If the Windows leg fails on Playwright browser download, re-run once before investigating; if it fails on a test, fix on the branch. `--with-deps` installs system libraries on Ubuntu; whether the Windows leg accepts the flag as a no-op is [TO CONFIRM] — if it errors, drop the flag for the Windows matrix entry.

### Task 29: Final verification and pull request

- [ ] **Step 1: Full local run on Windows**

Run: `$PY -m unittest -v`
Expected: every test OK or skipped with a stated reason; zero failures, zero errors.

- [ ] **Step 2: Live run**

Run: `.\p3dpreview.ps1 --root <folder with real Plant scripts>`. Exercise: pick a script, drag a slider hard back and forth (final model matches the final value), toggle Ports/Dims/Fixed dims (no server round trip in the network tab), add and delete a stray `.py` in the folder (overrides survive), save the script with a deliberate error (banner with highlighted line, empty params panel), fix it (re-renders), Section, Measure, Export GLB.

- [ ] **Step 3: Open the pull request**

```bash
gh pr create --title "Review fixes and enhancements" --body "$(cat <<'EOF'
Implements every item from the 2026-09-02 review: shim star-import fallback, empty-geometry warnings, full aqa.math, enum/bool/string params, sibling imports, per-render facet count, primitive dims; server hardening (unreadable folders, static path confinement, body validation, Condition-based SSE, LAN safety flag, port clash message); viewer request sequencing, no-flash swap, cached overlays, on-demand drawing, HiDPI resize fix, spin pivot, typed controls, escaping, URL hash state, render time, traceback highlight, Export GLB, Copy params, facet selector, section cut, measure tool; Windows launchers; README; CI; primitive coverage tests.

Plan: docs/superpowers/plans/2026-09-02-review-fixes.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Open decisions (owner to rule)

1. **Repository licence** — no `LICENSE` file is created by this plan. README carries `[TO CONFIRM]`.
2. **`demo.gif` (12 MB) in git history** — left as is. Rewriting history is out of scope.
3. **Plant syntax for `@enum` and the real `aqa.math` surface** — implemented against the shim's current acceptance and Python's `math`; marked `[TO CONFIRM]` in code and README.
4. **GitHub Actions version tags** — `actions/checkout@v4` and `actions/setup-python@v5` to be confirmed current before merge.

## Self-review against the 2026-09-02 review

| Review item | Task |
|---|---|
| 1 star-import placeholder | 2 |
| 2 unreadable folders kill browse/watcher | 9 |
| 3 static traversal | 10 |
| 4 malformed POST body | 10 |
| 5 empty solids silent | 3 |
| 6 vacuous test | 26 |
| 7 stale responses | 14 |
| 8 list events reset overrides | 15 |
| 9 overlay toggles re-render | 14 |
| 10 Fixed dims dead | 8, 18 |
| 11 spin detaches overlays | 16 |
| 12 error keeps old panel | 14 |
| 13 HiDPI resize loop | 16 |
| 14 typed params / allow_zero | 5, 17 |
| 15 innerHTML injection | 17 |
| 16 Windows launcher / 0.0.0.0 URL | 24, 12 |
| 17 stale README / docstrings | 9, 27 |
| Network exposure | 12 |
| SSE latency | 11 |
| ROOT lock | 11 |
| Sibling imports | 6, 15 |
| aqa.math subset | 4 |
| Port in use | 12 |
| gitignore / demo.gif / LICENSE / THIRD_PARTY / CI | 25, 28, open decisions |
| Test gaps | 10, 26 |
| Idle GPU | 16 |
| Enum/bool/string controls | 17 |
| URL hash | 19 |
| Section cut, measure | 22, 23 |
| Export, copy params | 20 |
| Traceback highlight, render time | 20 |
| Facet control | 7, 12, 21 |
| Windows launcher | 24 |
| Camera light | 16 |
