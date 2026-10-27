#!/usr/bin/env python3
"""Assemble and verify a full ps2build install kit from a successful edition build."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import zipfile

from build_edition import EDITIONS, ROOT, git

spec = importlib.util.spec_from_file_location("app_packager", ROOT / ".github/scripts/package_release_app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def package(edition, neutrino_archive):
    options = EDITIONS[edition]
    built = ROOT / "dist/editions" / edition
    manifest = json.loads((built / "BUILD-MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("configuration", "standard") != "standard":
        raise ValueError("configuration candidates cannot be packaged as standard releases")
    elf = built / "RIPTOPL.ELF"
    if manifest["edition"] != edition or manifest["source_commit"] != git("rev-parse", "HEAD"):
        raise ValueError("edition/source mismatch; rebuild before packaging")
    if manifest["dirty"] or git("status", "--porcelain"):
        raise ValueError("release packaging requires a clean source checkout and build")
    if manifest["elf_sha256"] != hashlib.sha256(elf.read_bytes()).hexdigest():
        raise ValueError("ELF no longer matches its build manifest")
    if manifest["compiler"] != "gcc":
        raise ValueError("published kits use GCC; LLVM artifacts are validation candidates")
    out = ROOT / "dist/releases" / edition
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output is not empty: {out}; use a fresh build workspace")
    out.mkdir(parents=True, exist_ok=True)
    app_name = "APP_RIPTOPL-RA" if options["ra"] else "APP_RIPTOPL"
    elf_name = "RIPTOPL-RA.ELF" if options["ra"] else "RIPTOPL.ELF"
    with tempfile.TemporaryDirectory(prefix="package-", dir=ROOT / "build") as temp:
        kit = Path(temp)
        for folder in ("POPS", "EMBER"):
            shutil.copytree(ROOT / "ship" / folder, kit / folder)
        for filename in ("CHEATS.TXT", "IGR_BG.TM2", "IGR_NO.TM2", "IGR_YES.TM2", "POPSTARTER.KELF", "TROJAN_7.BIN"):
            shutil.copyfile(app.EXAMPLE / "POPS" / filename, kit / "POPS" / filename)
        games = kit / "EMBER/games/Per-Game-Folder"
        games.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(app.EXAMPLE / "EMBER/games/Per-Game-Folder/GAME FILES", games / "GAME FILES")
        if (kit / "EMBER/bios.bin").exists():
            raise ValueError("Ember BIOS must not be redistributed")
        extractor = shutil.which("7z") or shutil.which("7za")
        if not extractor:
            raise ValueError("7z is required for the upstream Neutrino archive")
        # Inspect members before extraction; never allow an archive to leave its directory.
        listing = subprocess.check_output([extractor, "l", "-slt", str(neutrino_archive)], text=True)
        for line in listing.split("----------", 1)[-1].splitlines():
            if line.startswith("Path = "):
                name = line[7:].replace("\\", "/")
                if name.startswith("/") or ":" in name or ".." in name.split("/"):
                    raise ValueError(f"unsafe Neutrino archive path: {name}")
            if line.startswith(("Symbolic Link = ", "Hard Link = ")):
                raise ValueError("Neutrino archive contains a link")
        subprocess.run([extractor, "x", "-y", "-o" + str(kit / "neutrino"), str(neutrino_archive)], check=True, stdout=subprocess.DEVNULL)
        shutil.copyfile(ROOT / "ship/neutrino/bsd-udpfsbd.toml", kit / "neutrino/config/bsd-udpfsbd.toml")
        # i.LINK: Neutrino's own IEEE1394_bd_mini.irx loses its login after an IOP reset (original
        # #1018). Replace it with RiptOPL's build of the same driver -- the one the ELF embeds -- and
        # refuse to package if upstream stopped shipping the file bsd-ilink.toml loads.
        ilink = kit / "neutrino/modules/IEEE1394_bd_mini.irx"
        ours = built / "IEEE1394_bd_mini.irx"
        if not ilink.is_file() or hashlib.sha256(ours.read_bytes()).hexdigest() != manifest["ilink_bd_sha256"]:
            raise ValueError("cannot replace neutrino/modules/IEEE1394_bd_mini.irx (upstream file or RiptOPL build missing)")
        shutil.copyfile(ours, ilink)
        shortcuts = {name: name for name in ("PS2-Servers.url", "OrbitPS2-Manager.url", "OPL-PS1-AIO-Converter-GUI.url", "PS2RD-CHT-Manager.url")}
        shortcuts["android-udpfs-server.url"] = "udpfs-server.url"
        for target, source in shortcuts.items():
            shutil.copyfile(ROOT / "tools/pc" / source, kit / target)
        if options["ra"]:
            (kit / "xeRAbora.url").write_text("[InternetShortcut]\nURL=https://github.com/hacan359/xerabora/releases/tag/v0.1.0-alpha.10\n", encoding="utf-8")
        args = SimpleNamespace(package=str(kit), source_elf=str(elf), app_name=app_name, elf_name=elf_name,
            title="RiptOPL " + options["title"], pbt_title="RiptOPL " + options["title"],
            version=manifest["version"].split('"')[1], flavour="PS2BUILD", channel=options["title"],
            description="C++ ps2build migration; " + options["title"])
        app.stage(args)
        manifest["neutrino_archive"] = {"filename": neutrino_archive.name, "sha256": hashlib.sha256(neutrino_archive.read_bytes()).hexdigest()}
        for name in ("LICENSE", "CREDITS", "README.md"):
            shutil.copyfile(ROOT / name, kit / name)
        if options["ra"]:  # the RA ELF links mbedTLS (Apache-2.0): its licence travels with it
            shutil.copyfile(ROOT / "third_party/mbedtls/LICENSE", kit / "LICENSE-MBEDTLS.txt")
        manifest["kit_files"] = {p.relative_to(kit).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(kit.rglob("*")) if p.is_file()}
        (kit / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        archive = out / f"RIPTOPL-{options['title']}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted(kit.rglob("*")):
                if path.is_file():
                    zipped.write(path, path.relative_to(kit).as_posix())
        app.verify(SimpleNamespace(zip=str(archive), source_elf=str(elf), app_name=app_name, elf_name=elf_name, ra=options["ra"]))
        # RA resources must never enter either standard kit.
        if not options["ra"]:
            with zipfile.ZipFile(archive) as zipped:
                if any("raagent" in n.lower() or "orbit-ra" in n.lower() or "xerabora" in n.lower() for n in zipped.namelist()):
                    raise ValueError("RA resource leaked into a standard package")
        shutil.copyfile(kit / (app_name + ".psu"), out / (app_name + ".psu"))
        shutil.copyfile(kit / "BUILD-MANIFEST.json", out / "BUILD-MANIFEST.json")
    shutil.copyfile(elf, out / elf_name)
    subprocess.run(["git", "archive", "--format=zip", "--output=" + str(out / "RIPTOPL-src.zip"), manifest["source_commit"]], cwd=ROOT, check=True)
    sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file())
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    print(f"Verified {options['title']} release assets: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edition", choices=EDITIONS)
    parser.add_argument("--neutrino-archive", required=True, type=Path)
    args = parser.parse_args()
    try:
        package(args.edition, args.neutrino_archive.resolve())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
