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


if __name__ == "__main__":
    unittest.main()
