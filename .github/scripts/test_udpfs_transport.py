"""Run the production UDPFS transport and discovery stack against scripted IOP APIs."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[2]
NETWORK = ROOT / "modules/network"
TESTS = NETWORK / "udpfs_shared/tests"


def main():
    compiler = shlex.split(os.environ.get("CC", "cc"))
    common = ["-std=gnu99", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Werror",
              "-I" + str(TESTS / "stubs"),
              "-I" + str(NETWORK / "udpfs_ministack/include"),
              "-I" + str(NETWORK / "udpfs_smap/include")]
    targets = {target["name"]: target for target in yaml.safe_load((ROOT / "ps2.yaml").read_text())["targets"]}
    temporary = ROOT / "build/test-tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary) as directory:
        directory = Path(directory)

        def run(name, source, flags):
            binary = directory / (name + ".exe")
            subprocess.run([*compiler, *common, *flags, str(source), "-o", str(binary)], check=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=15)

        for variant in ("udpfs_ioman", "udpfs_bd"):
            # Compile through the same wrapper and header search paths as ps2.yaml.
            flags = ["-I" + str(ROOT / path) for path in targets[variant]["include_dirs"]]
            flags += ["-D" + value for value in targets[variant]["defines"]]
            production = NETWORK / variant / "src/udprdma.c"
            flags.append('-DUDPRDMA_TEST_SOURCE="' + production.as_posix() + '"')
            run(variant, TESTS / "test_udprdma_session.c", flags)
        run("announce", TESTS / "test_ministack_announce.c", [])
        run("conflict", TESTS / "test_ministack_conflict.c", [])
        run("xchg", TESTS / "test_ministack_xchg.c", ["-I" + str(NETWORK / "udpfs_ministack/src")])
        run("ack_wrap", NETWORK / "udpfs_ioman/tests/test_ack_sequence.c", [])
    print("PASS: UDPFS Files/IMG sessions, ACK wrap, discovery ARP, real IP-conflict handler and mstack: exchange")


if __name__ == "__main__":
    main()
