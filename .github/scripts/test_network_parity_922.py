"""Exercise the actual C++ DEV9/RA guards and UDPFS notice lifecycle from production #922."""
from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]


def compile_run(name, source):
    directory = ROOT / "build/test-tmp"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        src, exe = Path(tmp) / (name + ".cpp"), Path(tmp) / (name + ".exe")
        src.write_text(source, encoding="utf-8")
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        subprocess.run([*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=15)


ranet = read("src/sources/ranet.cpp")
compile_run("nic_reservation", r'''
#include <cassert>
enum { NET_PROTO_OFF, NET_PROTO_SMB, NET_PROTO_UDPFS, NET_PROTO_UDPFSBD, NET_PROTO_UDPBD, NET_PROTO_HTTP };
static int gNetworkProtocol, loaded;
class Ranet { public: static int nicBusy() { return loaded; } static int nicReserved(); };
''' + function(ranet, "int Ranet::nicReserved()") + r'''
int main() {
    for (int protocol = NET_PROTO_OFF; protocol <= NET_PROTO_HTTP; ++protocol) {
        gNetworkProtocol = protocol;
        for (loaded = 0; loaded <= 1; ++loaded) {
            bool udp = protocol == NET_PROTO_UDPFS || protocol == NET_PROTO_UDPFSBD || protocol == NET_PROTO_UDPBD;
            assert(Ranet::nicReserved() == (loaded || udp));
        }
    }
}
''')
for signature in ("int Ranet::askPc(", "int Ranet::netTestLink("):
    before_socket = function(ranet, signature).split("openPcSocket(")[0]
    assert "if (nicReserved())" in before_socket and "if (nicBusy())" not in before_socket
launch = function(ranet, "void Ranet::launchNetworkUp()")
assert "if (nicBusy())" in launch and "nicReserved()" not in launch

system = read("src/platform/system.cpp")
compile_run("dev9_retry", r'''
#include <cassert>
#include <cstddef>
#define LOG(...) ((void)0)
#define DDIOC_OFF 1
static unsigned char dev9Initialized, dev9Loaded, dev9InitCount;
static int result = -1, attempts, powered_off, ps2dev9_irx, size_ps2dev9_irx;
int sysLoadModuleBuffer(void*, int, int, void*) { ++attempts; return result; }
int fileXioDevctl(const char*, int, void*, int, void*, int) { ++powered_off; return 0; }
''' + function(system, "int sysInitDev9(void)") + function(system, "void sysShutdownDev9(void)") + r'''
int main() {
    assert(!sysInitDev9());
    assert(attempts == 1 && dev9InitCount == 1 && !dev9Initialized);
    sysShutdownDev9();
    assert(dev9InitCount == 0 && powered_off == 0);
    result = 0;
    assert(sysInitDev9());
    assert(attempts == 2 && dev9Initialized && dev9Loaded);
    assert(sysInitDev9());
    assert(attempts == 2 && dev9InitCount == 2);
    sysShutdownDev9();
    assert(powered_off == 0);
    sysShutdownDev9();
    assert(powered_off == 1 && dev9InitCount == 0);
}
''')
assert "int sysInitDev9(void);" in read("include/system.h")
udpfs = read("src/sources/udpfssupport.cpp")
loader = function(udpfs, "static void udpfsLoadModules(void)")
assert loader.index("if (!sysInitDev9())") < loader.index("&udpfs_smap_irx")
assert "sysShutdownDev9();\n        return;" in loader
bdm = read("src/sources/bdmsupport.cpp")
for signature in ("int BdmSupport::ensureNetworkSourceModules(int protocol, u32 timeoutMs)", "void bdmLoadBlockDeviceModules(void)"):
    chain = function(bdm, signature)
    assert chain.index("int dev9Ready = sysInitDev9();") < chain.index("if (!dev9Ready)") < chain.index("&udpfs_smap_irx") < chain.index("&smap_udpbd_irx")
    assert "sysShutdownDev9();" in chain

compile_run("conflict_notice", r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#define LOG(...) ((void)0)
#define UDPFS_DEVCTL_IP_CONFLICT 0x55460001
#define _STR_UDPFS_IP_CONFLICT 1
const char* _l(int) { return "IP conflict"; }
static int udpfsIpConflictWarned, udpfsIomanModLoaded, conflict, queries, notices;
static volatile int udpfsIpConflictNotice;
static char udpfsIpConflictText[320];
static int ps2_ip[] = {192,168,1,10};
int fileXioDevctl(const char*, int cmd, void*, int, void* buffer, int size) {
    assert(cmd == UDPFS_DEVCTL_IP_CONFLICT && size == 6);
    ++queries;
    memset(buffer, 0xab, 6);
    return conflict;
}
namespace host { struct UI { void warning(const char* text, int seconds) {
    ++notices;
    assert(seconds == 10 && strstr(text, "192.168.1.10") && strstr(text, "AB:AB:AB:AB:AB:AB"));
} }; UI& ui() { static UI value; return value; } }
''' + function(udpfs, "static void udpfsCheckIpConflict(void)") + function(udpfs, "void udpfsShowPendingNotice(void)") + r'''
int main() {
    udpfsCheckIpConflict(); assert(queries == 0);
    udpfsIomanModLoaded = 1;
    udpfsCheckIpConflict(); assert(queries == 1 && !udpfsIpConflictNotice);
    conflict = 1;
    udpfsCheckIpConflict(); assert(queries == 2 && udpfsIpConflictNotice && notices == 0);
    udpfsShowPendingNotice(); assert(notices == 1 && !udpfsIpConflictNotice);
    udpfsCheckIpConflict(); udpfsShowPendingNotice();
    assert(queries == 2 && notices == 1);
}
''')
assert "udpfsShowPendingNotice();" in function(read("src/app/opl.cpp"), "void menuUpdateHook()")
assert "#define UDPFS_DEVCTL_IP_CONFLICT 0x55460001" in udpfs
ioman = read("modules/network/udpfs_ioman/src/udpfs_ioman.c")
assert "#define UDPFS_DEVCTL_IP_CONFLICT 0x55460001" in ioman
assert "arp_ip_conflict(" in function(ioman, "static int udpfs_devctl(")
assert "I_arp_ip_conflict" in read("modules/network/udpfs_ioman/src/imports.lst")
assert "I_arp_ip_conflict" not in read("modules/network/udpfs_bd/src/imports.lst")
assert "DECLARE_IMPORT(7, arp_ip_conflict)" in read("modules/network/udpfs_ministack/include/mstack.h")
# Pin the positional ID while permitting later features to append their own labels.
labels = re.findall(r"^- label: (.+)$", read("lng/tmpl/_base.yml"), re.M)
assert labels.index("UDPFS_IP_CONFLICT") == 669  # generated enum ID 670 follows _STR_LOCALE
print("PASS: actual C++ NIC reservation, DEV9 retry/refcount and one-shot GUI notice; three DEV9 gates and IOP ABI")
