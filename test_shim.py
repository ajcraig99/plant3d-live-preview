import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from testutil import render_temp_script  # noqa: E402


class ShimTests(unittest.TestCase):
    def test_helper_renders_a_box(self):
        result = render_temp_script(
            "smoke_box",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                BOX(s, L=20.0, W=10.0, H=6.0)
            """,
        )
        self.assertEqual(result["meta"]["solid_count"], 1)
        self.assertTrue(result["glb"])

    def test_unmodelled_primitive_via_star_import_draws_placeholder(self):
        result = render_temp_script(
            "arcpart",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                ARC3D(s, R=50.0, A=90.0)
            """,
        )
        meta = result["meta"]
        self.assertEqual(meta["solid_count"], 1)
        self.assertEqual(len(meta["warnings"]), 1)
        self.assertIn("ARC3D", meta["warnings"][0])
        self.assertIn("placeholder", meta["warnings"][0])

    def test_star_import_does_not_leak_manifold_class(self):
        with self.assertRaises(Exception) as ctx:
            render_temp_script(
                "leakcheck",
                """
                from varmain.primitiv import *
                from varmain.custom import *

                @activate(Group="Test", LengthUnit="mm")
                def {stem}(s, **kw):
                    Manifold.cube([1, 1, 1], True)
                """,
            )
        self.assertIn("NameError", str(ctx.exception))

    def test_zero_radius_cylinder_warns_instead_of_vanishing_silently(self):
        result = render_temp_script(
            "zero_cyl",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                CYLINDER(s, R=0.0, H=10.0)
            """,
        )
        meta = result["meta"]
        self.assertEqual(meta["solid_count"], 0)
        self.assertEqual(len(meta["warnings"]), 1)
        self.assertIn("CYLINDER", meta["warnings"][0])
        self.assertIn("no geometry", meta["warnings"][0])

    def test_aqa_math_exposes_full_python_math_surface(self):
        result = render_temp_script(
            "mathuse",
            """
            from varmain.primitiv import *
            from varmain.custom import *
            from aqa.math import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                r = log10(1000.0) * 10.0          # 30
                assert isclose(asRadiants(180.0), pi)
                assert isfinite(hypot(3.0, 4.0, 12.0))
                SPHERE(s, R=r)
            """,
        )
        self.assertEqual(result["meta"]["solid_count"], 1)
        self.assertEqual(result["meta"]["warnings"], [])

    def test_describe_params_surfaces_enum_options_and_typed_defaults(self):
        result = render_temp_script(
            "enumpart",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            @param(KIND=ENUM, TooltipShort="Kind")
            @enum(KIND=["A", "B", "C"])
            @param(FLAG=BOOL, TooltipShort="Flag")
            @param(TAG=STRING, TooltipShort="Tag")
            @param(D=LENGTH, TooltipShort="Diameter")
            def {stem}(s, KIND="A", FLAG=True, TAG="x", D=20.0, **kw):
                SPHERE(s, R=D / 2.0)
            """,
        )
        by_name = {p["name"]: p for p in result["meta"]["params"]}
        self.assertEqual(by_name["KIND"]["enum"], ["A", "B", "C"])
        self.assertEqual(by_name["KIND"]["default"], "A")
        self.assertIsNone(by_name["D"]["enum"])
        self.assertIs(by_name["FLAG"]["default"], True)
        self.assertEqual(by_name["TAG"]["default"], "x")
        self.assertEqual(by_name["D"]["type"], "LENGTH")
        self.assertFalse(by_name["D"]["allow_zero"])

    def test_script_can_import_sibling_helper_and_sees_helper_edits(self):
        import tempfile
        from testutil import write_script
        from render import render_script
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "helper_sizes.py"), "w") as f:
                f.write("SIZE = 20.0\n")
            path = write_script(td, "usehelper", """
                from varmain.primitiv import *
                from varmain.custom import *
                from helper_sizes import SIZE

                @activate(Group="Test", LengthUnit="mm")
                def {stem}(s, **kw):
                    BOX(s, L=SIZE, W=10.0, H=6.0)
                """)
            first = render_script(path)["meta"]["bounds"]
            # BOX L runs along Plant Y, which the exporter maps to viewer -Z.
            self.assertAlmostEqual(first["max"][2] - first["min"][2], 20.0, places=5)

            with open(os.path.join(td, "helper_sizes.py"), "w") as f:
                f.write("SIZE = 40.0\n")
            second = render_script(path)["meta"]["bounds"]
            self.assertAlmostEqual(second["max"][2] - second["min"][2], 40.0, places=5)

    def test_segments_argument_controls_mesh_density(self):
        src = """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                CYLINDER(s, R=10.0, H=20.0)
            """
        coarse = render_temp_script("segcyl", src, segments=16)
        fine = render_temp_script("segcyl", src, segments=96)
        self.assertEqual(coarse["meta"]["segments"], 16)
        self.assertEqual(fine["meta"]["segments"], 96)
        self.assertLess(len(coarse["glb"]), len(fine["glb"]))


if __name__ == "__main__":
    unittest.main()
