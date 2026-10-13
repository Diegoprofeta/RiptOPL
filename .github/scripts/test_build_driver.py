"""SDK version gate, compiler path preservation and overlay cleanup."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[2]
TEMP_DIR = ROOT / "build/test-tmp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
SPEC = importlib.util.spec_from_file_location("build_driver", ROOT / "tools/build.py")
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


class BuildDriverTests(unittest.TestCase):
    def setUp(self):
        version = patch.object(driver.subprocess, "check_output", return_value="ps2build v2026.10.12.2\n")
        version.start()
        self.addCleanup(version.stop)

    def test_overlay_preserves_project_settings_without_workaround(self):
        original = yaml.safe_load((ROOT / "ps2.yaml").read_text())
        captured = []

        def compile_project(command, cwd):
            config = Path(command[command.index("--config") + 1])
            captured.append(config)
            self.assertEqual(config.parent, ROOT)
            self.assertEqual(cwd, ROOT)
            generated = yaml.safe_load(config.read_text())
            self.assertEqual(generated, original)
            self.assertNotIn("-sys-header-deps", config.read_text())
            return 1  # Failed builds must also remove the temporary config.

        with patch.object(driver.subprocess, "call", side_effect=compile_project):
            self.assertEqual(driver.build("llvm", "build/llvm", original), 1)
        self.assertFalse(captured[0].exists())

    def test_both_compilers_use_original_configuration_without_overlay(self):
        for compiler in ("gcc", "llvm"):
            with patch.object(driver.subprocess, "call", return_value=0) as run:
                self.assertEqual(driver.build(compiler, "build/" + compiler), 0)
            self.assertEqual(run.call_args.args[0][-2:], ["--config", str(ROOT / "ps2.yaml")])

    def test_old_or_unknown_sdk_fails_before_compiling(self):
        for version in ("ps2build v2026.10.12.1", "ps2build v2026.10.12", "ps2build dev"):
            with patch.object(driver.subprocess, "check_output", return_value=version), patch.object(driver.subprocess, "call") as run:
                with self.assertRaisesRegex(RuntimeError, "run ps2build update"):
                    driver.build("llvm", "build/llvm")
                run.assert_not_called()
        with patch.object(driver.subprocess, "check_output", return_value="ps2build v2026.10.13"):
            driver.require_supported_sdk()

    def test_launch_failure_removes_temporary_configuration(self):
        with tempfile.TemporaryDirectory(dir=TEMP_DIR) as directory:
            root = Path(directory)
            (root / "ps2.yaml").write_text("targets: [{name: test, cflags: []}]")
            with patch.object(driver, "ROOT", root), patch.object(driver.subprocess, "call", side_effect=OSError("launch failed")):
                with self.assertRaises(OSError):
                    driver.build("llvm", "build", {"targets": [{"name": "test", "cflags": []}]})
            self.assertEqual(list(root.iterdir()), [root / "ps2.yaml"])


if __name__ == "__main__":
    unittest.main()
