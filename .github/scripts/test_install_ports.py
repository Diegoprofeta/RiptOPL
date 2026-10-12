"""Port setup must select the requested compiler and preserve a good prior install."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("install_ports", ROOT / "tools/install_ports.py")
ports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ports)


def release(*names):
    return {"tag_name": "v1", "assets": [{"name": name, "browser_download_url": "https://example.com/" + name}
                                         for name in names]}


def archive(extra=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("package.yaml", "name: ogg\n")
        package.writestr("lib/libogg.a", b"new archive")
        package.writestr("LICENSE", "upstream license")
        if extra:
            package.writestr(extra, "unexpected")
    return stream.getvalue()


class InstallPortsTests(unittest.TestCase):
    def test_selection_does_not_depend_on_release_asset_order(self):
        metadata = release("ogg-v1-llvm.zip", "ogg-v1-gcc.zip")
        self.assertTrue(ports.select_asset(metadata, "ogg", "gcc").endswith("-gcc.zip"))
        self.assertTrue(ports.select_asset(metadata, "ogg", "llvm").endswith("-llvm.zip"))

    def test_legacy_archive_is_only_accepted_for_gcc(self):
        metadata = release("ogg-v1.zip")
        self.assertTrue(ports.select_asset(metadata, "ogg", "gcc").endswith("ogg-v1.zip"))
        with self.assertRaisesRegex(ValueError, "no unique llvm"):
            ports.select_asset(metadata, "ogg", "llvm")

    def test_missing_and_duplicate_compiler_archives_are_rejected(self):
        for metadata in (release("ogg-v1-gcc.zip"), release("ogg-v1-llvm.zip", "ogg-v1-llvm.zip")):
            with self.assertRaises(ValueError):
                ports.select_asset(metadata, "ogg", "llvm")

    def test_unsafe_archive_does_not_replace_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory)
            target = sdk / "packages-llvm/world/ogg"
            target.mkdir(parents=True)
            (target / "previous.txt").write_text("keep")
            metadata = json.dumps(release("ogg-v1-llvm.zip")).encode()
            with patch.object(ports, "download", side_effect=[metadata, archive("../escape.txt")]):
                with self.assertRaises(ValueError):
                    ports.install(sdk, "ogg", "llvm")
            self.assertEqual((target / "previous.txt").read_text(), "keep")
            self.assertFalse((sdk / "packages-llvm/world/escape.txt").exists())

    def test_llvm_install_preserves_gcc_package_and_license(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory)
            gcc = sdk / "packages/world/ogg"
            gcc.mkdir(parents=True)
            (gcc / "previous.txt").write_text("gcc")
            metadata = json.dumps(release("ogg-v1-llvm.zip")).encode()
            with patch.object(ports, "download", side_effect=[metadata, archive()]):
                ports.install(sdk, "ogg", "llvm")
            self.assertEqual((gcc / "previous.txt").read_text(), "gcc")
            self.assertEqual((sdk / "packages-llvm/world/ogg/LICENSE").read_text(), "upstream license")
            self.assertEqual((sdk / "packages-llvm/world/ogg/lib/libogg.a").read_bytes(), b"new archive")

    def test_failed_replacement_restores_previous_package(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory)
            target = sdk / "packages-llvm/world/ogg"
            target.mkdir(parents=True)
            (target / "previous.txt").write_text("keep")
            metadata = json.dumps(release("ogg-v1-llvm.zip")).encode()
            rename = Path.rename

            def fail_install(path, destination):
                if path.name == "new":
                    raise OSError("simulated replacement failure")
                return rename(path, destination)

            with patch.object(ports, "download", side_effect=[metadata, archive()]), patch.object(Path, "rename", fail_install):
                with self.assertRaisesRegex(OSError, "simulated replacement"):
                    ports.install(sdk, "ogg", "llvm")
            self.assertEqual((target / "previous.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
