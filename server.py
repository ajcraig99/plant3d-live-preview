"""
server.py - live-reload preview server for Plant 3D custom scripts.

Run it, open the browser, pick a script. Edit the .py in your editor and hit
save: the model re-renders automatically. Drag the parameter sliders to explore
a fitting's design space without touching Plant 3D at all.

    python server.py                 # serve ./.. (repo root), open :8770
    python server.py --root DIR --port N --no-open

Endpoints:
    GET /                     viewer HTML
    GET /vendor/*, /viewer/*  static assets
    GET /api/scripts          JSON list of discovered scripts
    GET /api/render?script=REL&params=JSON   -> {meta, glb_b64}
    GET /api/events           text/event-stream; fires when any script changes
"""

import os
import sys
import json
import time
import base64
import threading
import webbrowser
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import render as R  # noqa: E402

# ---------------------------------------------------------------------------
# Config / state
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(_HERE, ".."))     # repo root by default
SCRIPT_DIRS = ["customfittings", "customsupports"]
_watch_version = 0
_watch_lock = threading.Lock()
_last_changed = ""


def discover_scripts():
    found = []
    for d in SCRIPT_DIRS:
        full = os.path.join(ROOT, d)
        if not os.path.isdir(full):
            continue
        for name in sorted(os.listdir(full)):
            if name.endswith(".py"):
                found.append(d + "/" + name)
    return found


def _script_mtimes():
    """Return the current script paths and mtimes used by the live watcher."""
    mtimes = {}
    for rel in discover_scripts():
        path = os.path.join(ROOT, rel)
        try:
            mtimes[path] = os.path.getmtime(path)
        except OSError:
            pass  # the file may have disappeared between listing and stat
    return mtimes


def _watch_change(previous, current):
    """Describe a snapshot change for the browser's live-reload handler."""
    if previous.keys() != current.keys():
        return "__scripts__"
    for path in sorted(current):
        if previous[path] != current[path]:
            return os.path.relpath(path, ROOT).replace(os.sep, "/")
    return None


def _safe_script_path(rel):
    """Resolve a script path from a client-supplied relative path, refusing
    anything that escapes ROOT."""
    rel = rel.replace("\\", "/").lstrip("/")
    full = os.path.abspath(os.path.join(ROOT, rel))
    if not full.startswith(ROOT + os.sep):
        raise ValueError("path escapes root")
    if not full.endswith(".py") or not os.path.isfile(full):
        raise ValueError("not a script: %s" % rel)
    return full


def watcher():
    """Poll scripts; notify clients about edits, additions, and deletions."""
    global _watch_version, _last_changed
    mtimes = _script_mtimes()
    while True:
        current = _script_mtimes()
        changed = _watch_change(mtimes, current)
        mtimes = current
        if changed:
            with _watch_lock:
                _watch_version += 1
                _last_changed = changed
        time.sleep(0.3)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # quiet

    # -- helpers -------------------------------------------------------------
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self._send(404, "not found", "text/plain")
            return
        self._send(200, data, ctype)

    # -- routes --------------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        q = urllib.parse.parse_qs(u.query)

        if path == "/" or path == "/index.html":
            self._send_file(os.path.join(_HERE, "viewer", "index.html"), "text/html; charset=utf-8")
        elif path.startswith("/vendor/") or path.startswith("/viewer/"):
            rel = path.lstrip("/")
            full = os.path.abspath(os.path.join(_HERE, rel))
            if not full.startswith(_HERE):
                self._send(403, "forbidden", "text/plain"); return
            ctype = "application/javascript" if full.endswith(".js") else "text/plain"
            self._send_file(full, ctype)
        elif path == "/api/scripts":
            self._send(200, json.dumps({"scripts": discover_scripts()}))
        elif path == "/api/render":
            self._handle_render(q)
        elif path == "/api/events":
            self._handle_events()
        else:
            self._send(404, "not found", "text/plain")

    def _handle_render(self, q):
        rel = (q.get("script") or [""])[0]
        params = {}
        if q.get("params"):
            try:
                params = json.loads(q["params"][0])
            except json.JSONDecodeError:
                pass
        try:
            full = _safe_script_path(rel)
        except ValueError as e:
            self._send(400, json.dumps({"error": str(e)})); return
        try:
            result = R.render_script(full, params)
        except R.RenderError as e:
            self._send(200, json.dumps({"error": str(e), "script": rel})); return
        except Exception as e:  # last-resort guard so the server never dies
            self._send(200, json.dumps({"error": "%s: %s" % (type(e).__name__, e)})); return

        glb_b64 = base64.b64encode(result["glb"]).decode("ascii") if result["glb"] else None
        self._send(200, json.dumps({"meta": result["meta"], "glb_b64": glb_b64}))

    def _handle_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = -1
        try:
            while True:
                with _watch_lock:
                    v, ch = _watch_version, _last_changed
                if v != last:
                    last = v
                    payload = json.dumps({"version": v, "changed": ch})
                    self.wfile.write(("data: %s\n\n" % payload).encode())
                    self.wfile.flush()
                else:
                    # heartbeat so proxies / the client keep the stream open
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main(argv):
    global ROOT
    import argparse
    ap = argparse.ArgumentParser(description="Plant 3D live preview server.")
    ap.add_argument("--root", default=ROOT, help="repo root containing custom* dirs")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args(argv)
    ROOT = os.path.abspath(args.root)

    threading.Thread(target=watcher, daemon=True).start()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = "http://%s:%d/" % (args.host, args.port)
    print("Plant 3D preview server running at", url)
    print("Watching:", ", ".join(os.path.join(ROOT, d) for d in SCRIPT_DIRS))
    print("Ctrl-C to stop.")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main(sys.argv[1:])
