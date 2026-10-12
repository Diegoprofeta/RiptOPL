#!/usr/bin/env python3
"""Build RiptOPL with ps2build, including project headers in LLVM dependencies."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parent.parent


def build(toolchain, out_dir, definition=None):
    config = ROOT / "ps2.yaml"
    command = ["ps2build", "build", "--toolchain", toolchain, "--out-dir", out_dir]
    if toolchain == "gcc" and definition is None:
        return subprocess.call([*command, "--config", str(config)], cwd=ROOT)

    # ps2build currently emits project paths as -isystem under LLVM. Its -MMD
    # therefore misses project headers. Clang gives -MMD precedence over -MD,
    # so request system-header dependencies explicitly through its cc1 option.
    if definition is None:
        definition = yaml.safe_load(config.read_text(encoding="utf-8"))
    if toolchain == "llvm":
        for target in definition["targets"]:
            target.setdefault("cflags", []).extend(["-Xclang", "-sys-header-deps"])
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
