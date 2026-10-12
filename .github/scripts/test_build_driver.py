"""LLVM build configuration must preserve paths and track project headers."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("build_driver", ROOT / "tools/build.py")
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


class BuildDriverTests(unittest.TestCase):
    def test_llvm_tracks_headers_and_preserves_project_settings(self):
        original = yaml.safe_load((ROOT / "ps2.yaml").read_text())
        captured = []

        def compile_project(command, cwd):
            config = Path(command[command.index("--config") + 1])
            captured.append(config)
            self.assertEqual(config.parent, ROOT)
            self.assertEqual(cwd, ROOT)
            generated = yaml.safe_load(config.read_text())
            for target in generated["targets"]:
                self.assertEqual(target["cflags"][-2:], ["-Xclang", "-sys-header-deps"])
                del target["cflags"][-2:]
                if not target["cflags"] and "cflags" not in next(t for t in original["targets"] if t["name"] == target["name"]):
                    del target["cflags"]
            self.assertEqual(generated, original)
            return 1  # Failed builds must also remove the temporary config.

        with patch.object(driver.subprocess, "call", side_effect=compile_project):
            self.assertEqual(driver.build("llvm", "build/llvm"), 1)
        self.assertFalse(captured[0].exists())

    def test_gcc_uses_original_configuration(self):
        with patch.object(driver.subprocess, "call", return_value=0) as run:
            self.assertEqual(driver.build("gcc", "build/gcc"), 0)
        self.assertEqual(run.call_args.args[0][-2:], ["--config", str(ROOT / "ps2.yaml")])

    def test_launch_failure_removes_temporary_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ps2.yaml").write_text("targets: [{name: test, cflags: []}]")
            with patch.object(driver, "ROOT", root), patch.object(driver.subprocess, "call", side_effect=OSError("launch failed")):
                with self.assertRaises(OSError):
                    driver.build("llvm", "build")
            self.assertEqual(list(root.iterdir()), [root / "ps2.yaml"])


if __name__ == "__main__":
    unittest.main()
