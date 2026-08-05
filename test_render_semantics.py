import io
import os
import sys
import tempfile
import textwrap
import unittest

import trimesh


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render import render_script  # noqa: E402


class RenderSemanticsTest(unittest.TestCase):
    def render_temp_script(self, stem, source):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, stem + ".py")
            with open(path, "w") as f:
                f.write(textwrap.dedent(source.format(stem=stem)))
            return render_script(path)

    def assert_bounds_close(self, meta, expected_min, expected_max):
        self.assertIsNotNone(meta["bounds"])
        for key, expected in (("min", expected_min), ("max", expected_max)):
            with self.subTest(bound=key):
                actual = meta["bounds"][key]
                self.assertEqual(len(actual), len(expected))
                for a, e in zip(actual, expected):
                    self.assertAlmostEqual(a, e, places=6)

    def glb_volume(self, result):
        self.assertTrue(result["glb"])
        loaded = trimesh.load(io.BytesIO(result["glb"]), file_type="glb")
        if isinstance(loaded, trimesh.Scene):
            mesh = loaded.to_geometry()
        else:
            mesh = loaded
        return abs(mesh.volume)

    def mesh_island_count(self, result):
        self.assertTrue(result["glb"])
        loaded = trimesh.load(io.BytesIO(result["glb"]), file_type="glb")
        if isinstance(loaded, trimesh.Scene):
            mesh = loaded.to_geometry()
        else:
            mesh = loaded
        return len(mesh.split(only_watertight=False))

    def test_translated_box_exports_expected_bounds(self):
        result = self.render_temp_script(
            "translated_box",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                BOX(s, L=20.0, W=10.0, H=6.0).translate((30.0, -20.0, 40.0))
            """,
        )
        meta = result["meta"]

        self.assertEqual(meta["solid_count"], 1)
        self.assertEqual(meta["warnings"], [])
        self.assertTrue(result["glb"])
        self.assert_bounds_close(
            meta,
            expected_min=[27.0, 35.0, 10.0],
            expected_max=[33.0, 45.0, 30.0],
        )

    def test_rotated_box_exports_expected_bounds(self):
        result = self.render_temp_script(
            "rotated_box",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                BOX(s, L=20.0, W=10.0, H=6.0).rotateZ(90).translate((30.0, -20.0, 40.0))
            """,
        )
        meta = result["meta"]

        self.assertEqual(meta["solid_count"], 1)
        self.assertEqual(meta["warnings"], [])
        self.assertTrue(result["glb"])
        self.assert_bounds_close(
            meta,
            expected_min=[20.0, 35.0, 17.0],
            expected_max=[40.0, 45.0, 23.0],
        )

    def test_rectangular_supports_use_plant_box_axes(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for rel in (
            "customsupports/supportpost.py",
            "customsupports/supportaframe.py",
            "customsupports/teepost.py",
        ):
            script_path = os.path.join(repo_root, rel)
            if not os.path.exists(script_path):
                continue
            with self.subTest(script=rel):
                result = render_script(script_path)
                meta = result["meta"]

                self.assertEqual(meta["solid_count"], 1)
                self.assertEqual(meta["warnings"], [])
                self.assertEqual(self.mesh_island_count(result), 1)

    def test_subtract_from_cuts_main_and_drops_cutter(self):
        result = self.render_temp_script(
            "box_with_cylindrical_cut",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                main = BOX(s, L=20.0, W=20.0, H=20.0)
                cutter = CYLINDER(s, R=4.0, H=30.0, O=0.0).translate((0.0, 0.0, -15.0))
                main.subtractFrom(cutter)
                cutter.erase()
            """,
        )
        meta = result["meta"]

        self.assertEqual(meta["solid_count"], 1)
        self.assertEqual(meta["warnings"], [])
        self.assertTrue(result["glb"])
        self.assert_bounds_close(
            meta,
            expected_min=[-10.0, -10.0, -10.0],
            expected_max=[10.0, 10.0, 10.0],
        )
        volume = self.glb_volume(result)
        self.assertGreater(volume, 6900.0)
        self.assertLess(volume, 7100.0)

    def test_united_operands_do_not_render_at_original_position(self):
        result = self.render_temp_script(
            "part_with_united_child",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                main = BOX(s, L=10.0, W=10.0, H=10.0)
                child = BOX(s, L=2.0, W=2.0, H=2.0).translate((100.0, 0.0, 0.0))
                main.uniteWith(child)
                main.translate((0.0, 0.0, 50.0))
            """,
        )
        meta = result["meta"]

        self.assertEqual(meta["solid_count"], 1)
        self.assertEqual(meta["warnings"], [])
        self.assertTrue(result["glb"])
        self.assert_bounds_close(
            meta,
            expected_min=[-5.0, 45.0, -5.0],
            expected_max=[101.0, 55.0, 5.0],
        )

    def test_boolean_operand_can_be_reused_without_being_exported(self):
        result = self.render_temp_script(
            "part_with_reused_cutter",
            """
            from varmain.primitiv import *
            from varmain.custom import *

            @activate(Group="Test", LengthUnit="mm")
            def {stem}(s, **kw):
                left = BOX(s, L=10.0, W=10.0, H=10.0)
                right = BOX(s, L=10.0, W=10.0, H=10.0).translate((30.0, 0.0, 0.0))
                cutter = BOX(s, L=40.0, W=2.0, H=20.0).translate((15.0, 0.0, 0.0))
                left.subtractFrom(cutter)
                right.subtractFrom(cutter)
            """,
        )
        meta = result["meta"]

        self.assertEqual(meta["solid_count"], 2)
        self.assertEqual(meta["warnings"], [])
        self.assertTrue(result["glb"])
        self.assert_bounds_close(
            meta,
            expected_min=[-5.0, -5.0, -5.0],
            expected_max=[35.0, 5.0, 5.0],
        )


if __name__ == "__main__":
    unittest.main()
