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
