"""The warning ratchet must see native Windows logs as well as Linux CI logs."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("warning_gate", ROOT / "tools/warning_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class WarningGateTests(unittest.TestCase):
    def counts(self, text, root, encoding="utf-8"):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "build.log"
            log.write_text(text, encoding=encoding)
            with patch.object(gate, "ROOT", root):
                return gate.parse(log)

    def test_unix_paths_with_spaces_and_header_deduplication(self):
        root = "/home/test/PS2 Projects/RiptOPL"
        warning = f"{root}/include/sample.h:4:2: warning: signed comparison [-Wsign-compare]\n"
        counts = self.counts(warning * 2, root)
        self.assertEqual(counts, {"include/sample.h|-Wsign-compare": 1})

    def test_windows_paths_in_utf8_and_powershell_logs(self):
        root = "C:/PS2 Projects/RiptOPL"
        text = (
            f"{root}/src/core/sample.cpp:8:3: warning: unused variable [-Wunused-variable]\n"
            "C:\\PS2 Projects\\RiptOPL\\include\\sample.h:4:2: warning: signed comparison [-Wsign-compare]\n"
        )
        expected = {"src/core/sample.cpp|-Wunused-variable": 1, "include/sample.h|-Wsign-compare": 1}
        for encoding in ("utf-8", "utf-8-sig", "utf-16"):
            with self.subTest(encoding=encoding):
                self.assertEqual(self.counts(text, root, encoding), expected)

    def test_external_sdk_and_downloaded_sources_stay_excluded(self):
        root = "C:/workspace/RiptOPL"
        text = "".join(f"{path}:1:1: warning: unused [-Wunused-variable]\n" for path in (
            "C:/SDK/include/example.h",
            "D:/SDK/include/example.h",
            f"{root}/modules/network/lwNBD/example.c",
            f"{root}-other/src/example.c",
        ))
        self.assertEqual(self.counts(text, root), {})

    def test_unclassified_diagnostics_still_count(self):
        root = "/workspace/RiptOPL"
        counts = self.counts(f"{root}/ee_core/src/asm.S:2:1: warning: assembler diagnostic\n", root)
        self.assertEqual(counts, {"ee_core/src/asm.S|(assembler diagnostic)": 1})

    def test_cli_rejects_a_new_warning_instead_of_reporting_zero(self):
        for encoding in ("utf-8", "utf-16"):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as directory:
                log = Path(directory) / "build.log"
                log.write_text(f"{ROOT}/src/core/warning_gate_probe.cpp:1:1: warning: unused [-Wunused-variable]\n",
                               encoding=encoding)
                result = subprocess.run([sys.executable, str(ROOT / "tools/warning_gate.py"), str(log), "--check"],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("src/core/warning_gate_probe.cpp|-Wunused-variable", result.stdout)


if __name__ == "__main__":
    unittest.main()
