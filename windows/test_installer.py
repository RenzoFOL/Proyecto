import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import install_leyka as installer


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "addons"
        self.target.mkdir()
        self.archive = self.root / "suite.zip"
        with zipfile.ZipFile(self.archive, "w") as archive:
            for module in installer.MODULES:
                archive.writestr(module + "/__manifest__.py", "{'name': 'Test'}")

    def test_install_and_backup(self):
        unrelated = self.target / "other_module"
        unrelated.mkdir()
        (unrelated / "keep.txt").write_text("keep")
        previous = self.target / installer.MODULES[0]
        previous.mkdir()
        (previous / "old.txt").write_text("old")
        backup = installer.install(self.archive, self.target)
        self.assertTrue((backup / installer.MODULES[0] / "old.txt").exists())
        self.assertEqual((unrelated / "keep.txt").read_text(), "keep")

    def test_reject_traversal_before_changes(self):
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr(installer.MODULES[0] + "/../../escape.txt", "bad")
        with self.assertRaises(ValueError):
            installer.install(self.archive, self.target)
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertFalse((self.root / "escape.txt").exists())

    def test_failure_restores_previous_modules(self):
        for module in installer.MODULES:
            (self.target / module).mkdir()
            (self.target / module / "old.txt").write_text("old")
        original = installer.shutil.move
        def fail_second(source, destination):
            if "leyka_stage_" in source and source.endswith(installer.MODULES[1]):
                raise OSError("Simulated copy failure")
            return original(source, destination)
        with patch.object(installer.shutil, "move", side_effect=fail_second):
            with self.assertRaises(OSError):
                installer.install(self.archive, self.target)
        for module in installer.MODULES:
            self.assertEqual((self.target / module / "old.txt").read_text(), "old")


if __name__ == "__main__":
    unittest.main()
