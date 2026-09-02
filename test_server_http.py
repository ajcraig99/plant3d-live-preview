import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

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

    def test_post_root_with_bad_content_length_is_400_not_a_hang(self):
        for bad in ("-1", str(server._MAX_BODY + 1)):
            with self.subTest(content_length=bad):
                status, data = self.request(
                    "POST", "/api/root", body=b"",
                    headers={"Content-Type": "application/json", "Content-Length": bad})
                self.assertEqual(status, 400)
                self.assertIn("Content-Length", json.loads(data)["error"])

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
        self.assertEqual(server._browser_url("::1", 8770), "http://[::1]:8770/")

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


if __name__ == "__main__":
    unittest.main()
