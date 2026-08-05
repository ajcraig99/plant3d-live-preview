"""
render.py - execute a Plant 3D custom-script .py file through the preview shim
and produce a glTF (GLB) mesh plus a metadata JSON describing parameters,
ports and dimensions.

Usable as a library (see render_script) or a CLI:

    python render.py path/to/script.py                       # -> script.glb + script.json
    python render.py path/to/script.py -o out.glb
    python render.py path/to/script.py -p D=80 L=150
"""

import os
import sys
import json
import inspect
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHIM = os.path.join(_HERE, "shim")
if _SHIM not in sys.path:
    sys.path.insert(0, _SHIM)

import numpy as np                      # noqa: E402
import trimesh                          # noqa: E402
from manifold3d import Manifold         # noqa: E402
from p3dkernel import Scene             # noqa: E402

# Steel-ish palette; index 0 is the "main" body, extras get distinct shades so
# separate solids (guide plates, linestop bars, ...) are visually separable.
_PALETTE = [
    [0.62, 0.66, 0.70, 1.0],   # steel
    [0.70, 0.55, 0.35, 1.0],   # brass
    [0.45, 0.60, 0.75, 1.0],   # blue steel
    [0.55, 0.70, 0.50, 1.0],   # green
    [0.75, 0.55, 0.55, 1.0],   # copper
    [0.60, 0.55, 0.70, 1.0],   # violet
]


class RenderError(Exception):
    pass


def _load_entry(path):
    """Import the script module and return (module, entry_function)."""
    path = os.path.abspath(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    modname = "p3d_script_" + stem
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RenderError("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)

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


def describe_params(fn):
    """Merge @param metadata with the function signature defaults into an
    ordered list the UI can render."""
    meta = getattr(fn, "_p3d_meta", {}) or {}
    pmeta = meta.get("params", {})
    sig = inspect.signature(fn)
    out = []
    for i, (name, sp) in enumerate(sig.parameters.items()):
        if i == 0:
            continue  # the scene 's'
        if sp.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        default = sp.default if sp.default is not inspect.Parameter.empty else 0.0
        info = pmeta.get(name, {})
        out.append({
            "name": name,
            "default": default,
            "type": info.get("type", "LENGTH"),
            "short": info.get("short", name),
            "long": info.get("long", ""),
            "allow_negative": info.get("allow_negative", False),
            "allow_zero": info.get("allow_zero", True),
        })
    return out


def _mesh_to_trimesh(m, color):
    mesh = m.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    faces = np.asarray(mesh.tri_verts, dtype=np.int64)
    tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    tm.visual = trimesh.visual.ColorVisuals(
        tm, face_colors=np.tile(np.array(color) * 255, (len(faces), 1)).astype(np.uint8))
    return tm


def render_script(path, params=None):
    """Run the script and return a dict with keys:
        glb   : bytes (GLB) or None if empty
        meta  : dict (params schema, values used, ports, dims, warnings, bounds)
    Raises RenderError on load/exec failure (message is user-facing)."""
    mod, fn = _load_entry(path)
    schema = describe_params(fn)
    values = {p["name"]: p["default"] for p in schema}
    if params:
        for k, v in params.items():
            if k in values:
                values[k] = v

    s = Scene()
    try:
        fn(s, **values)
    except Exception as e:
        import traceback
        raise RenderError("script raised %s: %s\n%s" % (
            type(e).__name__, e, traceback.format_exc()))

    live = s.live_solids()
    scene = trimesh.Scene()
    for i, solid in enumerate(live):
        color = _PALETTE[i % len(_PALETTE)]
        try:
            scene.add_geometry(_mesh_to_trimesh(solid.m, color), node_name="solid_%d" % i)
        except Exception as e:  # a degenerate boolean result; skip but note it
            s.warnings.append("solid #%d failed to mesh: %s" % (i, e))

    if len(scene.geometry) == 0:
        glb = None
        bounds = None
    else:
        # glTF is Y-up; Plant/AutoCAD is Z-up. Rotate -90 about X so the model
        # sits the right way up in the viewer.
        scene.apply_transform(trimesh.transformations.rotation_matrix(
            -np.pi / 2.0, [1, 0, 0]))
        glb = scene.export(file_type="glb")
        b = scene.bounds
        bounds = {"min": b[0].tolist(), "max": b[1].tolist()}

    meta = {
        "script": os.path.basename(path),
        "entry": fn.__name__,
        "activate": (getattr(fn, "_p3d_meta", {}) or {}).get("activate", {}),
        "params": schema,
        "values": values,
        "ports": s.points,
        "dims": s.dims,
        "warnings": s.warnings,
        "solid_count": len(live),
        "bounds": bounds,
    }
    return {"glb": glb, "meta": meta}


def _parse_kv(items):
    out = {}
    for it in items or []:
        if "=" not in it:
            continue
        k, v = it.split("=", 1)
        try:
            out[k.strip()] = float(v)
        except ValueError:
            out[k.strip()] = v
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Render a Plant 3D custom script to GLB.")
    ap.add_argument("script")
    ap.add_argument("-o", "--out", help="output .glb path (default: <script>.glb)")
    ap.add_argument("-p", "--param", nargs="*", default=[], help="overrides like D=80 L=150")
    args = ap.parse_args(argv)

    result = render_script(args.script, _parse_kv(args.param))
    base = os.path.splitext(args.out or args.script)[0]
    if result["glb"] is None:
        print("WARNING: no geometry produced")
    else:
        out = args.out or (base + ".glb")
        with open(out, "wb") as f:
            f.write(result["glb"])
        print("wrote", out, "(%d bytes)" % len(result["glb"]))
    with open(base + ".json", "w") as f:
        json.dump(result["meta"], f, indent=2)
    print("wrote", base + ".json")
    for w in result["meta"]["warnings"]:
        print("  warn:", w)


if __name__ == "__main__":
    main(sys.argv[1:])
