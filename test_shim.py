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


if __name__ == "__main__":
    unittest.main()
