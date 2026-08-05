# Plant 3D Live Preview

A browser-based live renderer for Plant 3D custom Python parts. Point it at a
repo containing `customfittings/` and/or `customsupports/` directories, edit a
`.py`, hit **save**, and the 3D model re-renders in the browser in ~200 ms —
no Windows, no Plant 3D, no slow rebuild cycle. Drag parameter sliders to
explore a fitting's design space live.

The point: the **exact same, unmodified** script that ships to Plant 3D runs
here. No porting, no separate model definition.

![what it looks like: a shaded fitting, a port arrow, a dimension label, and a
parameter panel on the right]

## How it works

Plant 3D embeds its own Python with a geometry API (`varmain.primitiv`,
`varmain.custom`, `aqa.math`). This tool ships a drop-in **shim** for that API
(`shim/`) that executes those same calls on the [`manifold3d`](https://github.com/elalish/manifold)
mesh-CSG kernel, exports the result to glTF, and renders it with three.js.

```
your_script.py  ──►  shim (varmain / aqa)  ──►  manifold3d CSG  ──►  GLB
       ▲                                                               │
       │  edit + save                                       three.js viewer
       └──────────────  live reload (SSE watch)  ◄──────────────────────┘
```

### Fidelity to Plant's quirks

Plant's API is famously confusing — notably `main.subtractFrom(cutter)` means
`main = main - cutter` (the *caller* keeps the result), not what the name
suggests. The shim reproduces the behaviour the working repo scripts are written
against, so **what you see here is what Plant produces**, not a "corrected"
version. All boolean semantics live in one place: `shim/p3dkernel.py`. If a Plant
quirk ever needs to be mirrored more precisely, that's the only file to touch.

## Usage

```bash
./p3dpreview --root /path/to/your/plant3d/repo   # must contain customfittings/ or customsupports/
# first run creates a venv + installs deps, then opens the browser
```

Then:

- **Left panel** — click any script to load it. New or deleted `.py` files appear
  automatically while the preview server is running.
- **Middle** — orbit (drag), zoom (wheel), pan (right-drag). Toolbar toggles the
  grid, port arrows (blue), dimension lines (orange), wireframe, spin; **Frame**
  recentres; **Reset params** clears your slider overrides.
- **Right panel** — every `@param` becomes a labelled slider + number box, built
  from the script's own metadata (tooltips included). Changes re-render instantly.
- **Live reload** — the green dot by "Scripts" means the file watcher is
  connected. Save the current script in your editor and it re-renders. Untouched
  params follow the file's (possibly edited) defaults; params you've dragged keep
  your value across geometry edits.
- **Errors** — a script that raises shows the traceback in a red banner instead
  of failing silently. Unmodelled primitives draw a labelled placeholder and warn.

### Options

```bash
./p3dpreview --port 9000 --no-open
./p3dpreview --root /path/to/another/repo      # must contain custom* dirs
./p3dpreview --host 0.0.0.0                    # expose on the LAN
```

### One-off render from the CLI (no browser)

```bash
.venv/bin/python render.py /path/to/repo/customsupports/yourpart.py -p D=300 L=200
# -> yourpart.glb + yourpart.json (params schema, ports, dims, warnings, bounds)
```

## Coverage

Modelled primitives: `BOX`, `CYLINDER` (incl. hollow via `O=`, and tapered
`R1/R2`), `CONE`, `TORUS`, `SPHERE`, `HALFSPHERE`, `ELLIPSOIDHEAD`. Transforms
(`translate`, `rotateX/Y/Z`, `scale`), booleans (`uniteWith`, `subtractFrom`,
`intersectWith`), `erase`, `setPoint`, `setLinearDimension`, and the `aqa.math`
helpers (`asRadiants`, `tan`, `sqrt`, …) are all supported. Other Plant
primitives resolve to a labelled placeholder + warning so a script never
hard-crashes on an unmodelled call.

## Files

```
p3dpreview          launcher (venv bootstrap + server)
server.py           http server: viewer, /api/render, /api/scripts, SSE watch
render.py           run a script through the shim -> GLB + metadata (also a CLI)
shim/
  p3dkernel.py      Solid/Scene + primitives on manifold3d  (boolean semantics live here)
  varmain/primitiv.py   BOX/CYLINDER/CONE/TORUS/... (import target)
  varmain/custom.py     @activate/@group/@param/@enum + LENGTH/ANGLE/ENUM/INT/...
  aqa/math.py           trig (radians) + asRadiants + degrees rotate convention
viewer/index.html   three.js viewer (orbit, param panel, port/dim overlays)
vendor/             pinned three.js (offline; no CDN needed)
shot.py             optional: headless screenshot / self-test (needs playwright)
```

## Caveats

- This is a **mesh** preview (fast, robust booleans), not a B-rep. Geometry,
  proportions, ports and dimensions are faithful; it is not a manufacturing model.
- `CONE`'s `E=` (eccentricity) is treated as 0.
- Coordinate mapping: Plant is Z-up; the viewer is Y-up. The GLB and all overlay
  points are transformed consistently, so ports/dimensions line up with the mesh.
```
