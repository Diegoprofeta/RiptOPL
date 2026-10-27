"""Configuration ABI/driver isolation and rejection of variants at release boundaries."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TEMP_DIR = ROOT / "build/test-tmp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
import build_edition as editions
import package_edition
import publish_editions


class ConfigurationTests(unittest.TestCase):
    def targets(self, edition, configuration):
        return {t["name"]: t for t in editions.definition(edition, configuration)["targets"]}

    def test_all_configurations_preserve_edition_and_cross_module_abi(self):
        original = {name: editions.definition(name) for name in editions.EDITIONS}
        for edition in editions.EDITIONS:
            for configuration in editions.CONFIGURATIONS:
                with self.subTest(edition=edition, configuration=configuration):
                    if edition == "ra" and configuration == "ingamediag":
                        with self.assertRaisesRegex(ValueError, "RetroAchievements"):
                            self.targets(edition, configuration)
                        continue
                    targets = self.targets(edition, configuration)
                    diag = configuration == "ingamediag"
                    self.assertEqual("freezediag" in targets, diag)
                    self.assertEqual("freezediag" in targets["riptopl"]["embed_irx"], diag)
                    self.assertEqual("ee_core/src/freeze_diag.c" in targets["eecore"]["sources"], diag)
                    for target in targets.values():
                        self.assertEqual("INGAMEDIAG" in target.get("defines", []), diag and (
                            target["name"] in ("riptopl", "eecore", "cdvdfsv") or target["name"].endswith("_cdvdman")))
                    for name in ("riptopl", "eecore"):
                        self.assertEqual("RETROACHIEVEMENTS" in targets[name]["defines"], edition == "ra")
                        self.assertEqual("PADEMU" in targets[name]["defines"], configuration != "pademu0")
                        self.assertIn("GSM_1080P", targets[name]["defines"])
                    for name in ("bdm_mcemu", "mmce_mcemu", "hdd_mcemu", "smb_mcemu"):
                        self.assertEqual("PADEMU" in targets[name]["defines"], configuration != "pademu0")
                    loader = targets["riptopl"]
                    self.assertEqual("BUILTIN_KORIUM" in loader["defines"], edition != "incebtion")
                    self.assertEqual("raudp" in loader["embed_irx"], edition == "ra")
                    self.assertNotIn("ps2sdk_socket_compat", loader["libs"])
                    self.assertNotIn("ps2sdk_socket_compat", targets)
                    self.assertEqual("INGAME_UDP" in targets["SMSTCPIP"]["defines"], edition == "ra")
                    smap = targets["smap_ingame"]
                    self.assertEqual("RETROACHIEVEMENTS" in smap.get("defines", []), edition == "ra")
                    self.assertEqual("exports_tab" in smap, edition == "ra")
                    for target in targets.values():
                        for field in ("sources", "defines", "embed_irx", "libs"):
                            values = target.get(field, [])
                            self.assertEqual(len(values), len(set(values)), (target["name"], field))
            self.assertEqual(original[edition], editions.definition(edition))
        with self.assertRaisesRegex(ValueError, "unknown configuration"):
            editions.definition("korium", "invented")

    def test_controller_and_extras_resources(self):
        targets = self.targets("ra", "pademu0")
        loader = targets["riptopl"]
        self.assertTrue({"ds34usb_ee", "ds34bt_ee"}.isdisjoint(loader["libs"]))
        self.assertTrue({"usb_pademu", "bt_pademu", "ds34usb", "ds34bt"}.isdisjoint(loader["embed_irx"]))
        targets = self.targets("incebtion", "extras_ds5")
        self.assertIn("DS5_ENABLE", targets["ds34usb"]["defines"])
        self.assertNotIn("DS5_ENABLE", targets["ds34bt"].get("defines", []))
        self.assertIn("__RTL", targets["riptopl"]["defines"])
        for name in ("riptopl", "eecore"):
            self.assertIn("IGS", targets[name]["defines"])
        self.assertIn("ee_core/src/igs_api.c", targets["eecore"]["sources"])

    def test_debug_loader_and_ingame_transports_agree(self):
        for configuration in editions.CONFIGURATIONS:
            if "debug" not in configuration:
                continue
            targets = self.targets("ra", configuration)
            main, core = targets["riptopl"], targets["eecore"]
            uart = configuration.endswith("_uart")
            self.assertIn("TTY_PPC_UART" if uart else "TTY_UDP", main["defines"])
            self.assertIn("ppctty" if uart else "udptty", main["embed_irx"])
            self.assertIn("ioptrap", main["embed_irx"])
            if uart:
                self.assertNotIn("ps2link", targets)
                self.assertNotIn("ppctty", targets)  # Resolve the installed SDK driver.
                self.assertTrue((ROOT / "third_party/ps2sdk-ppctty/LICENSE").is_file())
                self.assertIn("sdk-world v2026.10.12.2", (ROOT / "third_party/ps2sdk-ppctty/UPSTREAM").read_text())
            else:
                self.assertIn("DEBUG", targets["ps2link"]["defines"])
            ingame = configuration.startswith(("ingame_", "iopcore_"))
            self.assertEqual("__LOAD_DEBUG_MODULES" in core["defines"], ingame)
            self.assertEqual("INGAME_DRIVER" in targets["SMSTCPIP"]["defines"], not ingame)
            if ingame:
                self.assertIn("TTY_PPC" if uart else "TTY_UDP", core["defines"])
                for name, target in targets.items():
                    if name.endswith("_cdvdman"):
                        dev9 = name != "pccf_cdvdman"  # PCCF exports its own dev9 table
                        self.assertEqual("__USE_DEV9" in target["defines"], dev9)
                        self.assertIn("__IOPCORE_DEBUG", target["defines"])
                        self.assertEqual("modules/iopcore/cdvdman/dev9.c" in target["sources"], dev9)
                self.assertEqual("DEBUG" in targets["bdm_mcemu"]["defines"], configuration.startswith("iopcore_"))
        dtl = self.targets("korium", "dtl")
        self.assertIn("udnl-t300:udnl", dtl["riptopl"]["embed_irx"])
        self.assertNotIn("udnl", dtl["riptopl"]["embed_irx"])
        for name in ("riptopl", "eecore"):
            self.assertIn("_DTL_T10000", dtl[name]["defines"])
        serial = self.targets("korium", "eesio_debug")
        self.assertIn("siocookie", serial["riptopl"]["libs"])
        self.assertIn("siocookie", serial["riptopl"]["headers"])

    def test_candidates_cannot_overwrite_release_or_other_configuration_stages(self):
        outputs, stages = set(), set()
        for edition in editions.EDITIONS:
            release_stage = editions.build_paths(edition, "gcc", "standard")[1]
            for configuration in editions.CONFIGURATIONS[1:]:
                for compiler in ("gcc", "llvm"):
                    output, stage = editions.build_paths(edition, compiler, configuration)
                    self.assertNotEqual(stage, release_stage)
                    self.assertNotIn(output, outputs)
                    self.assertNotIn(stage, stages)
                    outputs.add(output)
                    stages.add(stage)

    def test_llvm_igs_size_policy_preserves_other_compiler_configurations(self):
        for edition in editions.EDITIONS:
            for compiler in ("gcc", "llvm"):
                for configuration in ("standard", "extras", "extras_ds5", "debug"):
                    targets = {t["name"]: t for t in editions.definition(edition, configuration, compiler)["targets"]}
                    wanted = "-Oz" if compiler == "llvm" and configuration in ("extras", "extras_ds5") else "-Os"
                    self.assertEqual(targets["eecore"]["opt"], wanted)
                    self.assertEqual(targets["eecore"]["linkfile"], "ee_core/linkfile")

    def test_packager_refuses_configuration_before_touching_release_outputs(self):
        with tempfile.TemporaryDirectory(dir=TEMP_DIR) as directory:
            root = Path(directory)
            built = root / "dist/editions/korium"
            built.mkdir(parents=True)
            (built / "BUILD-MANIFEST.json").write_text(json.dumps({"configuration": "debug"}))
            with patch.object(package_edition, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "configuration candidates"):
                    package_edition.package("korium", root / "unused.7z")
            self.assertFalse((root / "dist/releases").exists())


class PublisherTests(unittest.TestCase):
    """Small synthetic kits exercise manifest/provenance checks, not PS2 acceptance."""
    sha = "1234567890abcdef" * 2 + "12345678"

    def kit(self, root, configuration="standard", dirty=False, source=None):
        for edition, options in editions.EDITIONS.items():
            path = root / ("release-" + edition)
            path.mkdir()
            elf = "RIPTOPL-RA.ELF" if options["ra"] else "RIPTOPL.ELF"
            psu = "APP_RIPTOPL-RA.psu" if options["ra"] else "APP_RIPTOPL.psu"
            app = "APP_RIPTOPL-RA" if options["ra"] else "APP_RIPTOPL"
            payload = b"\x7fELFsynthetic-test-only"
            manifest = {"repository": "NathanNeurotic/RiptOPL", "source_commit": source or self.sha,
                        "dirty": dirty, "edition": edition, "compiler": "gcc", "sdk": "ps2build",
                        "ra": options["ra"], "configuration": configuration,
                        "ps2build_version": "test", "components": {},
                        "elf_sha256": hashlib.sha256(payload).hexdigest()}
            (path / elf).write_bytes(payload)
            (path / psu).write_bytes(b"synthetic-psu")
            (path / "BUILD-MANIFEST.json").write_text(json.dumps(manifest))
            with zipfile.ZipFile(path / "RIPTOPL-src.zip", "w") as source_zip:
                source_zip.comment = (source or self.sha).encode()
                source_zip.writestr("README.md", "synthetic source")
            with zipfile.ZipFile(path / f"RIPTOPL-{options['title']}.zip", "w") as kit:
                kit.writestr("BUILD-MANIFEST.json", json.dumps(manifest))
                kit.writestr(f"APPS/{app}/{elf}", payload)
                kit.writestr(psu, b"synthetic-psu")
            sums = "".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in sorted(path.iterdir()))
            (path / "SHA256SUMS.txt").write_text(sums)

    def test_valid_standard_and_self_consistent_invalid_manifests(self):
        for kwargs in ({}, {"configuration": "debug"}, {"dirty": True}, {"source": "0" * 40}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory(dir=TEMP_DIR) as directory:
                root = Path(directory)
                self.kit(root, **kwargs)
                if kwargs:
                    with self.assertRaisesRegex(ValueError, "invalid source/edition manifest"):
                        publish_editions.verify(root, self.sha)
                else:
                    self.assertEqual(len(publish_editions.verify(root, self.sha)), 3)


if __name__ == "__main__":
    unittest.main()
