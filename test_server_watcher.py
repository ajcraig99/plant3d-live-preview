import os
import sys
import unittest


PREVIEW_DIR = os.path.dirname(os.path.abspath(__file__))
if PREVIEW_DIR not in sys.path:
    sys.path.insert(0, PREVIEW_DIR)

import server  # noqa: E402


class WatchChangeTests(unittest.TestCase):
    def setUp(self):
        self.original_root = server.ROOT
        server.ROOT = os.path.abspath(os.path.join(PREVIEW_DIR, ".."))

    def tearDown(self):
        server.ROOT = self.original_root

    def path(self, rel):
        return os.path.join(server.ROOT, *rel.split("/"))

    def test_added_script_refreshes_script_list(self):
        old = {self.path("customsupports/one.py"): 1.0}
        new = {**old, self.path("customsupports/two.py"): 1.0}
        self.assertEqual(server._watch_change(old, new), "__scripts__")

    def test_deleted_script_refreshes_script_list(self):
        old = {
            self.path("customsupports/one.py"): 1.0,
            self.path("customsupports/two.py"): 1.0,
        }
        new = {self.path("customsupports/one.py"): 1.0}
        self.assertEqual(server._watch_change(old, new), "__scripts__")

    def test_edited_script_rerenders_only_that_script(self):
        path = self.path("customsupports/one.py")
        self.assertEqual(
            server._watch_change({path: 1.0}, {path: 2.0}),
            "customsupports/one.py",
        )

    def test_unchanged_snapshot_does_not_notify(self):
        snapshot = {self.path("customsupports/one.py"): 1.0}
        self.assertIsNone(server._watch_change(snapshot, dict(snapshot)))


if __name__ == "__main__":
    unittest.main()
