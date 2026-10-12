#!/usr/bin/env python3
"""Build one release edition with ps2build; GCC/LLVM are compiler checks, not editions."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

from build import build

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = {
    "korium": {"title": "Korium", "tag": "rolling-korium", "theme": "korium", "ra": False},
    "ra": {"title": "RetroAchievements", "tag": "rolling-ra", "theme": "korium", "ra": True},
    "incebtion": {"title": "IncebtIon", "tag": "rolling-incebtion", "theme": "incebtion", "ra": False},
}


def add(target, field, *values):
    target.setdefault(field, []).extend(v for v in values if v not in target.get(field, []))


def definition(edition):
    options = EDITIONS[edition]
    config = yaml.safe_load((ROOT / "ps2.yaml").read_text(encoding="utf-8"))
    # YAML aliases share lists. Mutating one target must not change another.
    config["targets"] = [copy.deepcopy(t) for t in config["targets"]]
    targets = {t["name"]: t for t in config["targets"]}
    main, core = targets["riptopl"], targets["eecore"]
    if options["theme"] == "korium":
        add(main, "defines", "BUILTIN_KORIUM")
    if options["ra"]:
        for target in (main, core):
            add(target, "defines", "RETROACHIEVEMENTS")
        add(main, "sources", "src/platform/md5.c", *[
            f"src/sources/{name}.cpp" for name in ("rawatch", "rahash", "ranet", "rabadge", "discsupport")])
        add(core, "sources", "ee_core/src/ra.c", "ee_core/src/ra_overlay.c")
        main["embed_irx"] = ["smbman_ra:smbman" if v == "smbman" else v for v in main["embed_irx"]]
        add(main, "embed_irx", "raudp")
        add(targets["SMSTCPIP"], "defines", "INGAME_UDP")
        # sdk-core v2026.10.12.1 still omits these POSIX socket entry points.
        # Use the pinned SDK implementation, retaining its libc descriptor table.
        config["targets"].append({
            "name": "ps2sdk_socket_compat", "type": "ee_lib",
            "sources": ["third_party/ps2sdk-socket/socket.c"],
            "include_dirs": ["third_party/ps2sdk-socket"], "headers": ["cglue"],
            "defines": ["F_socket", "F_bind", "F_recvfrom", "F_sendto", "F_setsockopt"],
        })
        add(main, "libs", "ps2sdk_socket_compat")
        for name in ("bdm_cdvdman", "mmce_cdvdman"):
            add(targets[name], "defines", "__USE_DEV9")
            add(targets[name], "sources", "modules/iopcore/cdvdman/dev9.c")
    return config


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edition", choices=EDITIONS)
    parser.add_argument("--toolchain", choices=("gcc", "llvm"), default="gcc")
    args = parser.parse_args()
    os.chdir(ROOT)
    source = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    options = EDITIONS[args.edition]
    os.environ["RIPTOPL_EDITION"] = args.edition
    os.environ["LOCALVERSION"] = f"PS2BUILD-{options['title']}-{args.toolchain.upper()}"
    # Each edition regenerates blobs, so sequential local builds cannot inherit
    # a previous edition's RA mark, theme graphics, or displayed version.
    subprocess.run([sys.executable, "tools/assets.py", "embed"], check=True)
    subprocess.run([sys.executable, "tools/assets.py", "version"], check=True)
    config = definition(args.edition)
    canonical = yaml.safe_dump(config, sort_keys=False)
    output = Path("build/editions") / f"{args.edition}-{args.toolchain}"
    result = build(args.toolchain, str(output), config)
    if result:
        return result
    elf = output / "bin/riptopl-packed.elf"
    if not elf.is_file() or elf.read_bytes()[:4] != b"\x7fELF":
        raise ValueError(f"invalid packed ELF: {elf}")
    if git("rev-parse", "HEAD") != source or bool(git("status", "--porcelain")) != dirty:
        raise ValueError("source checkout changed during build")
    stage = ROOT / "dist/editions" / args.edition
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(elf, stage / "RIPTOPL.ELF")
    sdk = Path(os.environ.get("PS2BUILD_HOME", shutil.which("ps2build") or "")).resolve()
    if sdk.is_file():
        sdk = sdk.parent
    manifest = {
        "repository": "NathanNeurotic/RiptOPL", "source_commit": source, "dirty": dirty,
        "edition": args.edition, **options, "sdk": "ps2build", "compiler": args.toolchain,
        "ps2build_version": subprocess.check_output(["ps2build", "--version"], text=True).strip(),
        "components": yaml.safe_load((sdk / "versions.yaml").read_text()) if (sdk / "versions.yaml").exists() else {},
        "definition_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
        "version": (ROOT / "asm/opl_version.h").read_text().strip(),
        "run_url": os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/" +
            os.environ.get("GITHUB_REPOSITORY", "NathanNeurotic/RiptOPL") + "/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "local"),
    }
    (stage / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (stage / "ps2.resolved.yaml").write_text(canonical, encoding="utf-8")
    print(f"Built {options['title']}: {manifest['elf_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
