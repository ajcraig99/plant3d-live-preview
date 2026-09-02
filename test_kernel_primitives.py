import math
import os
import sys
import textwrap
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
    body = textwrap.dedent(body).strip()
    return HEADER + "\n" + "\n".join("        " + line for line in body.splitlines()) + "\n"


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
