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

    def test_fixed_dims_button_draws_primitive_dimensions(self):
        self.open()
        self.assertEqual(len(self.hook("lastMeta().primitive_dims")), 3)   # BOX: L, W, H
        base = self.hook("overlayCount()")
        self.page.click("#btnFixedDims")
        self.page.wait_for_timeout(200)
        # each dim line adds a line, two end dots and a label = 4 objects
        self.assertEqual(self.hook("overlayCount()"), base + 12)
        self.page.click("#btnFixedDims")

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

    def test_segments_select_changes_mesh_density(self):
        self.open()
        self.assertEqual(self.hook("lastMeta().segments"), server.R.Scene().segments)
        self.page.select_option("#segSel", "32")
        self.page.wait_for_function("window.__p3d.lastMeta().segments === 32", timeout=10000)


if __name__ == "__main__":
    unittest.main()
