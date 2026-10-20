"""Run the actual C++ IP rewrite against mcman's truncate contract and FAT control.

mcman_open2 only truncates an existing file in its O_CREAT branch. See
ps2dev/ps2sdk iop/memorycard/mcman/src/ps2mc_fio.c and original OPL #1010/#1011.
This tests new rewrites and their existing rollback, not damaged-tail recovery.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else
          ROOT / "src/platform/sysneutrino.cpp").read_text(encoding="utf-8")


def function(signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


functions = "\n".join(function(s) for s in (
    "static const char *sysLastPathSeparator(", "static int sysSyncNeutrinoUdpfsToml("))
program = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <string>
#define O_RDONLY 0x0001
#define O_WRONLY 0x0002
#define O_CREAT 0x0200
#define O_TRUNC 0x0400
#define LOG(...) ((void)0)
static int ps2_ip[4];
static std::string bytes, openedPath;
static bool mc, live;
static int pos, opens, writes, closes, failOpen, failWrite, writeResult, readResult;

static int fake_open(const char *path, int flags, ...) {
    assert(!live);
    openedPath = path;
    if (++opens == failOpen) return -1;
    if (flags & O_CREAT) {
        va_list args; va_start(args, flags);
        assert(va_arg(args, int) == 0666); va_end(args);
    }
    if ((flags & O_TRUNC) && (!mc || (flags & O_CREAT))) bytes.clear();
    live = true; pos = 0;
    return 0; // Descriptor zero is valid, including for restore.
}
static int fake_read(int fd, void *buffer, int size) {
    assert(fd == 0 && live);
    if (readResult < 0) return readResult;
    int count = (int)bytes.size() < size ? (int)bytes.size() : size;
    memcpy(buffer, bytes.data(), count);
    return count;
}
static int fake_write(int fd, const void *buffer, int size) {
    assert(fd == 0 && live);
    int count = ++writes == failWrite ? writeResult : size;
    if (count < 0) return count;
    if (count > size) count = size;
    if (pos + count > (int)bytes.size()) bytes.resize(pos + count);
    if (count) memcpy(&bytes[pos], buffer, count);
    pos += count;
    return count;
}
static int fake_close(int fd) { assert(fd == 0 && live); live = false; ++closes; return 0; }
#define open fake_open
#define read fake_read
#define write fake_write
#define close fake_close
@FUNCTIONS@

static std::string config(const char *ip) {
    return std::string("# custom file\n[[module]]\nfile = \"ministack.irx\"\nargs = [\"ip=") +
        ip + "\", \"x=keep\"]\nenv = [\"LE\", \"EE\"]"; // no final newline
}
static void reset(const std::string &text, bool card) {
    assert(!live); bytes = text; mc = card;
    pos = opens = writes = closes = failOpen = failWrite = writeResult = readResult = 0;
    ps2_ip[0] = 10; ps2_ip[1] = 0; ps2_ip[2] = 0; ps2_ip[3] = 5;
}
static int sync(const char *path, const char *device) {
    int rc = sysSyncNeutrinoUdpfsToml(path, device);
    assert(!live && closes == opens - (failOpen > 0 && opens >= failOpen));
    return rc;
}
int main() {
    for (bool card : {false, true}) {
        for (const char *path : {"mc0:/neutrino/neutrino.elf", "mc1:/NEUTRINO/neutrino.elf",
                                 "mass0:/neutrino/neutrino.elf", "host:neutrino\\neutrino.elf"}) {
            for (const char *device : {"udpfs", "udpfsbd"}) {
                reset(config("192.168.100.123"), card);
                assert(sync(path, device) == 0 && bytes == config("10.0.0.5"));
                std::string base(path);
                auto slash = base.find_last_of("/\\");
                assert(openedPath == base.substr(0, slash + 1) + "config" + base[slash] + "bsd-" + device + ".toml");
                assert(writes == 1);
                assert(sync(path, device) == 0 && writes == 1); // in sync: no recreation/write
                ps2_ip[0] = ps2_ip[1] = ps2_ip[2] = ps2_ip[3] = 255;
                assert(sync(path, device) == 0 && bytes == config("255.255.255.255"));
                ps2_ip[0] = 1; ps2_ip[1] = ps2_ip[2] = ps2_ip[3] = 0;
                assert(sync(path, device) == 0 && bytes == config("1.0.0.0"));
            }
        }
        const char *path = "mc0:/neutrino/neutrino.elf";
        const auto original = config("1.0.0.1");
        const auto longer = config("255.255.255.255");
        // A partial longer update can exceed the old file size. Restore must truncate too.
        for (int result : {-1, 0, (int)longer.size() - 1}) {
            reset(original, card);
            ps2_ip[0] = ps2_ip[1] = ps2_ip[2] = ps2_ip[3] = 255;
            failWrite = 1; writeResult = result;
            assert(sync(path, "udpfs") < 0 && bytes == original && writes == 2);
        }
        reset(original, card); failOpen = 2;
        assert(sync(path, "udpfs") == 0 && bytes == original && writes == 0); // existing read-only contract
        reset(original, card); failOpen = 1;
        assert(sync(path, "udpfs") < 0 && writes == 0);
        reset(original, card); readResult = -1;
        assert(sync(path, "udpfs") < 0 && bytes == original && writes == 0);
        reset("", card);
        assert(sync(path, "udpfs") < 0 && writes == 0);
        reset(std::string(4095, 'x'), card);
        assert(sync(path, "udpfs") == 0 && bytes.size() == 4095 && writes == 0);
        reset("name = \"custom, no IP token\"\n", card);
        assert(sync(path, "udpfs") == 0 && bytes == "name = \"custom, no IP token\"\n" && writes == 0);
        reset(original, card); failWrite = 1; writeResult = 5; failOpen = 3;
        assert(sync(path, "udpfs") < 0 && writes == 1); // failed restore still refuses handoff
        reset(original, card);
        assert(sync("neutrino.elf", "udpfs") == 0 && opens == 0 && bytes == original);
    }
    puts("PASS: C++ Neutrino TOML shrink/grow, no-op, paths, descriptor zero and rollback (MC/FAT)");
}
'''.replace("@FUNCTIONS@", functions)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    cpp = path / "tomlsync.cpp"
    exe = path / ("tomlsync.exe" if sys.platform == "win32" else "tomlsync")
    cpp.write_text(program, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(cpp), "-o", str(exe)], check=True, timeout=120)
    subprocess.run([str(exe)], check=True, timeout=10)
