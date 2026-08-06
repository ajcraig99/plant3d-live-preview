# Plant 3D Live Preview

A browser-based live renderer for Plant 3D custom Python parts. Point it at a
repo containing `customfittings/` and/or `customsupports/` directories, edit a
`.py`, hit **save**, and the 3D model re-renders in the browser.

![Plant 3D Live Preview demo](demo.gif)

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

## Coverage

Modelled primitives: `BOX`, `CYLINDER` (incl. hollow via `O=`, and tapered
`R1/R2`), `CONE`, `TORUS`, `SPHERE`, `HALFSPHERE`, `ELLIPSOIDHEAD`. Transforms
(`translate`, `rotateX/Y/Z`, `scale`), booleans (`uniteWith`, `subtractFrom`,
`intersectWith`), `erase`, `setPoint`, `setLinearDimension`, and the `aqa.math`
helpers (`asRadiants`, `tan`, `sqrt`, …) are all supported. Other Plant
primitives resolve to a labelled placeholder + warning so a script never
hard-crashes on an unmodelled call.

## Options

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

## Caveats

- This is a **mesh** preview (fast, robust booleans), not a B-rep. Geometry,
  proportions, ports and dimensions are faithful; it is not a manufacturing model.
- `CONE`'s `E=` (eccentricity) is treated as 0.
- Coordinate mapping: Plant is Z-up; the viewer is Y-up. The GLB and all overlay
  points are transformed consistently, so ports/dimensions line up with the mesh.
