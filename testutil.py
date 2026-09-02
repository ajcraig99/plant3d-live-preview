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
