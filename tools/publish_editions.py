#!/usr/bin/env python3
"""Publish the three already verified ps2build kits from an explicit workflow dispatch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

from build_edition import EDITIONS, git


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True).strip()


def verify(root, expected_sha):
    candidates = []
    suites = []
    for edition, options in EDITIONS.items():
        path = root / ("release-" + edition)
        manifest = json.loads((path / "BUILD-MANIFEST.json").read_text(encoding="utf-8"))
        if (manifest["repository"] != "NathanNeurotic/RiptOPL" or manifest["source_commit"] != expected_sha
                or manifest["dirty"] or manifest["edition"] != edition or manifest["compiler"] != "gcc"
                or manifest["sdk"] != "ps2build" or manifest["ra"] != options["ra"]):
            raise ValueError(f"invalid source/edition manifest for {edition}")
        suites.append((manifest["ps2build_version"], manifest["components"]))
        sums = {}
        for line in (path / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            if Path(name).name != name or name in sums:
                raise ValueError(f"unsafe or duplicate asset name: {name}")
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"checksum mismatch: {edition}/{name}")
            sums[name] = digest
        actual = {p.name for p in path.iterdir() if p.is_file()}
        elf = "RIPTOPL-RA.ELF" if options["ra"] else "RIPTOPL.ELF"
        psu = "APP_RIPTOPL-RA.psu" if options["ra"] else "APP_RIPTOPL.psu"
        required = {elf, psu, "BUILD-MANIFEST.json", "RIPTOPL-src.zip", f"RIPTOPL-{options['title']}.zip"}
        if set(sums) != required or actual != required | {"SHA256SUMS.txt"}:
            raise ValueError(f"unexpected release inventory: {edition}")
        if sums[elf] != manifest["elf_sha256"]:
            raise ValueError("published ELF differs from the tested build")
        with zipfile.ZipFile(path / "RIPTOPL-src.zip") as source:
            if source.testzip() or source.comment.decode() != expected_sha:
                raise ValueError("source snapshot differs from the built commit")
        with zipfile.ZipFile(path / f"RIPTOPL-{options['title']}.zip") as kit:
            if kit.testzip() or json.loads(kit.read("BUILD-MANIFEST.json")) != manifest:
                raise ValueError("install kit manifest differs from the standalone manifest")
            app_name = "APP_RIPTOPL-RA" if options["ra"] else "APP_RIPTOPL"
            if kit.read(f"APPS/{app_name}/{elf}") != (path / elf).read_bytes() or kit.read(psu) != (path / psu).read_bytes():
                raise ValueError("standalone assets differ from the verified install kit")
        candidates.append((edition, options, path, sums))
    if any(suite != suites[0] for suite in suites[1:]):
        raise ValueError("editions resolved different SDK suites; rebuild them together before publication")
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--check", action="store_true", help="verify only; never contact GitHub")
    args = parser.parse_args()
    sha = git("rev-parse", "HEAD")
    candidates = verify(args.artifacts, sha)
    if args.check:
        print(f"Verified all three channels at {sha}")
        return
    repo = "NathanNeurotic/RiptOPL"
    if (os.environ.get("GITHUB_REPOSITORY") != repo or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REF") != "refs/heads/rebuild/main" or os.environ.get("GITHUB_SHA") != sha):
        raise ValueError("publication is restricted to an explicit dispatch at rebuild/main")
    current = json.loads(gh("api", f"repos/{repo}/branches/rebuild/main"))["commit"]["sha"]
    if current != sha:
        raise ValueError("integration branch advanced during this run; publish its new tested head")
    for edition, options, path, sums in candidates:
        tag = options["tag"]
        notes = (f"RiptOPL {options['title']} — C++ / ps2build development build.\n\n"
                 f"Source: [{sha[:8]}](https://github.com/{repo}/commit/{sha}). "
                 "Release compiler: GCC. See BUILD-MANIFEST.json for the resolved SDK suite and SHA256SUMS.txt for asset verification.\n\n"
                 "Use the full install ZIP or the app PSU. Imported production documentation and passing builds do not establish console acceptance for this migration.\n\n"
                 "[Installation and guides](https://nathanneurotic.github.io/RiptOPL/) · "
                 f"[Wiki](https://github.com/{repo}/wiki)\n")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".md", delete=False) as stream:
            stream.write(notes)
            notes_path = Path(stream.name)
        try:
            exists = subprocess.run(["gh", "release", "view", tag, "--repo", repo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            assets = [str(p) for p in sorted(path.iterdir()) if p.is_file()]
            if exists:
                gh("release", "upload", tag, "--repo", repo, "--clobber", *assets)
            else:
                gh("release", "create", tag, "--repo", repo, "--target", sha, "--draft", "--title", options["title"], "--notes-file", str(notes_path), *assets)
            release = json.loads(gh("api", f"repos/{repo}/releases/tags/{tag}"))
            remote = {a["name"]: a for a in release["assets"]}
            for asset in assets:
                file = Path(asset)
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                item = remote.get(file.name, {})
                if item.get("size") != file.stat().st_size or item.get("digest") != "sha256:" + digest:
                    raise ValueError(f"GitHub did not retain the verified asset: {tag}/{file.name}")
            gh("api", f"repos/{repo}/git/refs/tags/{tag}", "-X", "PATCH", "-f", "sha=" + sha, "-F", "force=true")
            gh("release", "edit", tag, "--repo", repo, "--title", options["title"], "--notes-file", str(notes_path),
               "--draft=false", "--prerelease=false", "--latest=" + ("true" if edition == "korium" else "false"))
            reference = json.loads(gh("api", f"repos/{repo}/git/ref/tags/{tag}"))
            if reference["object"]["sha"] != sha:
                raise ValueError(f"release tag drifted: {tag}")
            print(f"Published and verified {tag} at {sha}")
        finally:
            notes_path.unlink()


if __name__ == "__main__":
    main()
