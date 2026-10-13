"""Port setup must select the requested compiler and preserve a good prior install."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
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
    def test_timeout_during_response_read_retries_from_a_new_request(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [TimeoutError("partial response"), b"complete archive"]
        with patch.object(ports.urllib.request, "urlopen", return_value=response) as opened, patch.object(ports.time, "sleep") as sleep:
            self.assertEqual(ports.download("https://example.com/package.zip"), b"complete archive")
        self.assertEqual(opened.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_transient_http_errors_retry_but_missing_release_does_not(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"metadata"
        for status in (429, 503, 404):
            error = ports.urllib.error.HTTPError("https://example.com/release", status, "failed", None, None)
            with patch.object(ports.urllib.request, "urlopen", side_effect=[error, response]) as opened, patch.object(ports.time, "sleep") as sleep:
                if status == 404:
                    with self.assertRaises(ports.urllib.error.HTTPError):
                        ports.download("https://example.com/release")
                    self.assertEqual(opened.call_count, 1)
                    sleep.assert_not_called()
                else:
                    self.assertEqual(ports.download("https://example.com/release"), b"metadata")
                    self.assertEqual(opened.call_count, 2)
                    sleep.assert_called_once_with(1)

    def test_persistent_timeout_stops_after_three_attempts(self):
        with patch.object(ports.urllib.request, "urlopen", side_effect=TimeoutError("offline")) as opened, patch.object(ports.time, "sleep") as sleep:
            with self.assertRaises(TimeoutError):
                ports.download("https://example.com/release")
        self.assertEqual(opened.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

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

    def test_failed_rollback_keeps_recoverable_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory)
            target = sdk / "packages-llvm/world/ogg"
            target.mkdir(parents=True)
            (target / "previous.txt").write_text("keep")
            metadata = json.dumps(release("ogg-v1-llvm.zip")).encode()
            rename = Path.rename

            def fail_install_and_restore(path, destination):
                if path.name in ("new", "previous"):
                    raise OSError("simulated locked destination")
                return rename(path, destination)

            with patch.object(ports, "download", side_effect=[metadata, archive()]), patch.object(Path, "rename", fail_install_and_restore):
                with self.assertRaises(OSError):
                    ports.install(sdk, "ogg", "llvm")
            backups = list(target.parent.glob(".ogg-*/previous/previous.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
