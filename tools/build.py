#!/usr/bin/env python3
"""Build RiptOPL with the released ps2build project-header dependency fix."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parent.parent
MINIMUM_VERSION = (2026, 10, 12, 2)


def require_supported_sdk():
    version = subprocess.check_output(["ps2build", "--version"], text=True).strip()
    match = re.search(r"\bv(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?\b", version)
    if match is None or tuple(int(v or 0) for v in match.groups()) < MINIMUM_VERSION:
        raise RuntimeError(f"ps2build v2026.10.12.2 or newer is required (found {version}); run ps2build update")


def build(toolchain, out_dir, definition=None):
    require_supported_sdk()
    config = ROOT / "ps2.yaml"
    command = ["ps2build", "build", "--toolchain", toolchain, "--out-dir", out_dir]
    if definition is None:
        return subprocess.call([*command, "--config", str(config)], cwd=ROOT)

    temporary = None
    try:
        # Keep the config beside ps2.yaml so relative project paths resolve alike.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".yaml",
                                         prefix=".ps2build-", dir=ROOT, delete=False) as stream:
            temporary = Path(stream.name)
            yaml.safe_dump(definition, stream, sort_keys=False)
        return subprocess.call([*command, "--config", str(temporary)], cwd=ROOT)
    finally:
        if temporary is not None:
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", choices=("gcc", "llvm"),
                        default=os.environ.get("PS2BUILD_TOOLCHAIN", "gcc"))
    parser.add_argument("--out-dir", default="build")
    args = parser.parse_args()
    return build(args.toolchain, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
