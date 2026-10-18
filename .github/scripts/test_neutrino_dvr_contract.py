"""Exercise actual DVR preflight without loading drivers or touching hardware."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hostmap  # noqa: F401 - translate the production host UI interface for this harness

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "src/platform/sysneutrino.cpp").read_text(encoding="utf-8")


def function(signature):
    """Extract a production function, including its control flow and path bounds."""
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


functions = "\n\n".join(function(s) for s in (
    "static const char *getDeviceName(", "static int neutrinoArgHasActiveFlag(",
    "static int neutrinoEffectiveBsdfs(", "static const char *sysLastPathSeparator(",
    "static int sysNeutrinoDvrPreflight(", "int sysNeutrinoPreflight(",
))
harness = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <set>
#include <vector>
#define LOG(...) ((void)0)
#define NET_BOOT_UDPFS 2
#define O_RDONLY 0
enum { _STR_NEUTRINO_DEV_UNSUPPORTED=1, _STR_NEUTRINO_BD_NO_DEVICE_NUMBER,
       _STR_NEUTRINO_TOML_SYNC_FAILED, _STR_NEUTRINO_DVR_QUICKBOOT,
       _STR_NEUTRINO_DVR_BACKEND_ARGS, _STR_NEUTRINO_DVR_FILE_MISSING };
static char gNeutrinoArgs[256];
static std::set<std::string> files;
static std::set<int> live;
static std::vector<std::string> opened;
static int warning, missing, closes, nextFd, messageId;
static std::string missingPath;
static int bdmGetLoadedNetProtocol() { return 0; }
static const char *_l(int id) { messageId=id; return "DVR companion missing"; }
static void guiWarning(const char *, int) { ++warning; }
static void guiMsgBoxMissing(const char *, const char *path) { ++missing; missingPath=path; }
static int sysSyncNeutrinoUdpfsToml(const char *, const char *) { assert(false); return -1; }
static int open(const char *path, int flags) {
    assert(flags==O_RDONLY); opened.emplace_back(path);
    if (!files.count(path)) return -1;
    live.insert(++nextFd); return nextFd;
}
static int close(int fd) { assert(live.erase(fd)==1); ++closes; return 0; }
@FUNCTIONS@
static void reset(const char *base="mc0:/NEUTRINO/") {
    assert(live.empty()); files.clear(); opened.clear(); warning=missing=closes=nextFd=0;
    missingPath.clear(); gNeutrinoArgs[0]=0; messageId=0;
    files.insert(std::string(base)+"config/bsd-dvr.toml");
    for (auto m: {"dvrdrv.irx", "dvrfile.irx", "dvrfile_fhi.irx"})
        files.insert(std::string(base)+"modules/"+m);
}
static int preflight(const char *extra=nullptr, const char *path="mc0:/NEUTRINO/neutrino.elf") {
    return sysNeutrinoPreflight("dvr",path,3,extra,-1);
}
int main() {
    reset(); assert(!strcmp(getDeviceName("dvr"),"dvr"));
    assert(!strcmp(getDeviceName("dvr0"),"unsupported"));
    assert(preflight()==0 && opened.size()==4 && closes==4 && !warning && !missing);
    assert(neutrinoEffectiveBsdfs("dvr",3,nullptr)==0);
    for (const char *flag: {"-qb", "-bsdfs=bd", "-bsd=ata", "-bsd=dvr"}) {
        reset(); snprintf(gNeutrinoArgs,sizeof(gNeutrinoArgs),"%s",flag);
        assert(preflight()<0 && warning==1 && opened.empty());
        assert(messageId==(!strcmp(flag,"-qb") ? _STR_NEUTRINO_DVR_QUICKBOOT : _STR_NEUTRINO_DVR_BACKEND_ARGS));
        reset(); assert(preflight(flag)<0 && warning==1 && opened.empty());
    }
    for (const char *inactive: {"$-qb", "--b -qb", "-qb-extra", "--b -bsdfs=bd", "$-bsd=ata"}) {
        reset(); assert(preflight(inactive)==0 && closes==4);
    }
    // A --b in global arguments does not disable per-game Neutrino options.
    reset(); strcpy(gNeutrinoArgs,"--b tail"); assert(preflight("-qb")<0 && opened.empty());
    reset(); files.erase("mc0:/NEUTRINO/config/bsd-dvr.toml");
    files.insert("mc0:/NEUTRINO/bsd-dvr.toml");
    assert(preflight()==0 && opened.size()==5 && closes==4);
    for (const char *absent: {"config/bsd-dvr.toml", "modules/dvrdrv.irx", "modules/dvrfile.irx", "modules/dvrfile_fhi.irx"}) {
        reset(); std::string path=std::string("mc0:/NEUTRINO/")+absent; files.erase(path);
        assert(preflight()<0 && missing==1 && live.empty());
        assert(missingPath==(strstr(absent,".toml") ? "mc0:/NEUTRINO/bsd-dvr.toml" : path));
    }
    reset(); assert(preflight(nullptr,"neutrino.elf")<0 && opened.empty() && missing==1);
    reset(); files.clear();
    files.insert(R"(mc0:\NEUTRINO\config\bsd-dvr.toml)");
    for (auto m: {"dvrdrv.irx", "dvrfile.irx", "dvrfile_fhi.irx"})
        files.insert(std::string(R"(mc0:\NEUTRINO\modules\)")+m);
    assert(preflight(nullptr,R"(mc0:\NEUTRINO\neutrino.elf)")==0 && closes==4);
    reset(); std::string longPath="mc0:/"+std::string(400,'a')+"/neutrino.elf";
    assert(preflight(nullptr,longPath.c_str())<0 && opened.empty() && missing==1);
    reset(); assert(sysNeutrinoPreflight("dvr",nullptr,0,nullptr,-1)<0 && opened.empty());
    // Standard paths neither inspect DVR files nor gain a new device-number requirement.
    reset(); assert(sysNeutrinoPreflight("usb","mass0:/neutrino.elf",0,nullptr,-1)==0 && opened.empty());
    puts("PASS: DVR preflight rejects unsafe active flags and incomplete companions before teardown; no driver/hardware IO");
}
'''.replace("@FUNCTIONS@", functions)
with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "dvr.cpp"
    exe = Path(tmp) / ("dvr.exe" if os.name == "nt" else "dvr")
    src.write_text(harness, encoding="utf-8")
    sanitizers = ["-fsanitize=address,undefined", "-fno-pie", "-no-pie"] if os.name != "nt" else []
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *sanitizers,
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
