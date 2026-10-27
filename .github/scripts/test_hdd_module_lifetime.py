"""Host regression: repeated ATA readiness probes must not inflate DEV9 ownership.

Compiles the real HddSupport::loadModules / shutdownSupportModules / shutdownBaseModules
(src/sources/hddsupport.cpp) as C++ with stub IOP drivers and exercises boot probes, page
teardown/re-entry, terminal shutdown and retry after a failed ATAD load. No HDD or physical
PS2 is touched. Ported from the original's test of the same name.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / "src/sources/hddsupport.cpp").read_text(encoding="utf-8")


def extract(signature):
    start = source.index(signature)
    opening = source.index("{", start)
    level = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            level += 1
        elif source[i] == "}":
            level -= 1
            if level == 0:
                return source[start:i + 1]
    raise AssertionError("unclosed function: " + signature)


functions = "\n\n".join(extract(s) for s in (
    "int HddSupport::loadModules(",
    "void HddSupport::shutdownSupportModules(",
    "void HddSupport::shutdownBaseModules(",
))

harness = r"""
#include <stdio.h>
#include <stddef.h>

enum {
    HDD_LOADMODULES_STATUS_ERROR = -2,
    HDD_LOADMODULES_STATUS_UNK = -1,
    HDD_LOADMODULES_STATUS_NOERROR,
    HDD_LOADMODULES_STATUS_ALREADYLOADED,
    HDD_LOADMODULES_STATUS_BUSYLOADING
};
#define HDD_PFS_DIAG_NOT_RUN (-9999)
#define ERROR_HDD_IF_NOT_DETECTED 400
#define _STR_HDD_NOT_CONNECTED_ERROR 1
#define PDIOC_CLOSEALL 1
#define LOG(...) do { if (0) printf(__VA_ARGS__); } while (0)

namespace host {
struct App { void setError(int, int) {} };
static App &app() { static App a; return a; }
}

struct HddSupport {
    unsigned char hdProKitDetected = 0, modulesLoadCount = 0, modulesLoaded = 0, supportModulesLoaded = 0;
    int loadModules();
    void shutdownSupportModules();
    void shutdownBaseModules();
    void diagBootStageBegin(const char *) {}
    void diagBootStageEnd(const char *, int) {}
    void diagBootStageEndVoid(const char *) {}
};

static int gDeinitTerminal;
static char *gHDDPrefix;
static int bdm_irx, hdpro_atad_irx, ps2atad_irx, xhdd_irx;
static int size_bdm_irx, size_hdpro_atad_irx, size_ps2atad_irx, size_xhdd_irx;

static int initDev9, shutdownDev9, idleOps, flushOps, loadCalls, failAtad;
static int sysInitDev9(void) { initDev9++; return 1; }
static void sysShutdownDev9(void) { shutdownDev9++; }
static int hddCheckHDProKit(void) { return 0; }
static int sysLoadModuleBuffer(void *p, int, int, const char *)
{
    loadCalls++;
    if (p == &ps2atad_irx && failAtad) {
        failAtad = 0;
        return -1;
    }
    return 0;
}
static void DelayThread(int) {}
static int fileXioDevctl(const char *, int, void *, int, void *, int) { return 0; }
static void hddFlushCache(void) { flushOps++; }
static void hddSetIdleImmediate(void) { idleOps++; }

@FUNCTIONS@

#define CHECK(cond, msg) do { if (!(cond)) { puts("FAIL: " msg); return 1; } } while (0)

static void shutdown(HddSupport &h)
{
    h.shutdownSupportModules();
    h.shutdownBaseModules();
}

int main(void)
{
    HddSupport h;
    int i;
    CHECK(h.loadModules() == HDD_LOADMODULES_STATUS_NOERROR, "first ATA probe loads drivers");
    for (i = 0; i < 20; i++)
        CHECK(h.loadModules() == HDD_LOADMODULES_STATUS_ALREADYLOADED, "resident ATA probe returns ready");
    CHECK(h.modulesLoadCount == 1 && initDev9 == 1, "repeated probes do not acquire more DEV9 owners");
    CHECK(loadCalls == 3, "drivers are loaded only on the first probe");

    gDeinitTerminal = 0;
    shutdown(h);
    CHECK(h.modulesLoadCount == 0 && idleOps == 0, "non-terminal shutdown must not idle ATA under BDM");
    CHECK(shutdownDev9 == 0, "non-terminal shutdown preserves DEV9 for other devices");

    CHECK(h.loadModules() == HDD_LOADMODULES_STATUS_ALREADYLOADED, "page reentry reuses resident ATA");
    CHECK(h.modulesLoadCount == 1 && initDev9 == 1, "reentry does not acquire a second DEV9 owner");

    gDeinitTerminal = 1;
    shutdown(h);
    CHECK(h.modulesLoadCount == 0 && idleOps == 1, "terminal shutdown idles ATA once");
    CHECK(shutdownDev9 == 1, "terminal shutdown releases DEV9 exactly once");
    shutdown(h);
    CHECK(shutdownDev9 == 1 && idleOps == 1, "repeated shutdown does not release DEV9 twice");

    /* New IOP generation, one failed first load, then retry. */
    h.modulesLoaded = h.modulesLoadCount = 0;
    failAtad = 1;
    CHECK(h.loadModules() == HDD_LOADMODULES_STATUS_ERROR, "failed ATAD load is an error");
    CHECK(h.modulesLoadCount == 0 && shutdownDev9 == 2, "failed load releases owner and can retry");
    CHECK(h.loadModules() == HDD_LOADMODULES_STATUS_NOERROR, "retry succeeds");
    CHECK(h.modulesLoadCount == 1 && initDev9 == 3, "retry acquires one DEV9 owner");
    shutdown(h);
    CHECK(shutdownDev9 == 3, "retry's owner released once on terminal shutdown");

    h.modulesLoaded = 0;
    h.modulesLoadCount = 1; /* another thread is initializing */
    i = loadCalls;
    CHECK(h.loadModules() == HDD_LOADMODULES_STATUS_BUSYLOADING, "in-progress load is not ready");
    CHECK(h.modulesLoadCount == 1 && loadCalls == i, "busy probe does not change ownership");
    puts("HDD: idempotent ATA probes, retry and DEV9 release verified");
    return 0;
}
"""

with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / "hdd_modules.cpp"
    exe = Path(tmp) / "hdd_modules"
    c.write_text(harness.replace("@FUNCTIONS@", functions), encoding="utf-8")
    cc = subprocess.run(
        ["c++", "-Wall", "-Werror", "-Wno-unused-function", "-Wno-unused-variable",
         "-Wno-unused-parameter", str(c), "-o", str(exe)],
        capture_output=True, text=True
    )
    if cc.returncode:
        print(cc.stderr)
        sys.exit(cc.returncode)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
