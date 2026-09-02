import os
import sys
import tempfile
import unittest
from unittest import mock


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


class DiscoveryHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d, name in (("alpha", "a.py"), ("locked", "b.py")):
            os.makedirs(os.path.join(self.root, d))
            open(os.path.join(self.root, d, name), "w").close()
        open(os.path.join(self.root, "top.py"), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def _listdir_denying(self, denied_suffix):
        real = os.listdir

        def fake(path="."):
            if str(path).replace("\\", "/").endswith(denied_suffix):
                raise PermissionError(13, "Access is denied", str(path))
            return real(path)
        return fake

    def test_discover_scripts_skips_unreadable_subfolder(self):
        with mock.patch("server.os.listdir", side_effect=self._listdir_denying("/locked")):
            self.assertEqual(server.discover_scripts(self.root), ["top.py", "alpha/a.py"])

    def test_discover_scripts_returns_empty_for_unreadable_root(self):
        with mock.patch("server.os.listdir", side_effect=PermissionError(13, "denied")):
            self.assertEqual(server.discover_scripts(self.root), [])

    def test_dir_entries_survive_unreadable_children(self):
        with mock.patch("server.os.listdir", side_effect=self._listdir_denying("/locked")):
            entries = {e["name"]: e["has_scripts"] for e in server._dir_entries(self.root)}
        self.assertEqual(entries, {"alpha": True, "locked": False})

    def test_watch_poll_swallows_errors(self):
        # _watch_poll is one iteration of the watcher loop; it must never raise.
        with mock.patch("server._snapshot", side_effect=RuntimeError("disk went away")):
            self.assertEqual(server._watch_poll({}), {})


if __name__ == "__main__":
    unittest.main()
