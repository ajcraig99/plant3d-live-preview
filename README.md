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
