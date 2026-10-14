"""Exercise the real cluster writer and abort/status calls during a device IO window."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else root / "modules/vmc/genvmc/genvmc.c").read_text(encoding="utf-8")
start = source.index("static int mc_writecluster(")
function = source[start:source.index("\n}\n", start) + 3]
program = r'''
#include <assert.h>
#include <string.h>
#include "modules/vmc/genvmc/genvmc.h"
#define DPRINTF(...) ((void)0)
typedef struct { int cluster_size; } MCDevInfo;
static MCDevInfo devinfo = {1024};
static int genvmc_abort_sema = 1, genvmc_abort, tokens = 1, writeResult, writes, failSeek, interruptIo;
static statusVMCparam_t genvmc_stats;
static int vmc_abort(void);
static int vmc_status(statusVMCparam_t *param);
static int WaitSema(int id) { assert(id == 1 && tokens == 1); tokens--; return 0; }
static int SignalSema(int id) { assert(id == 1 && tokens == 0); tokens++; return 0; }
static void serviceDuringIo(int boundary) {
    assert(tokens == 1); // slow device IO must not hold the abort semaphore
    if (interruptIo == boundary) {
        statusVMCparam_t status;
        assert(vmc_abort() == 0 && genvmc_abort);
        assert(vmc_status(&status) == 0 && status.VMC_status == GENVMC_STAT_BUSY);
        assert(tokens == 1); // the worker remains busy until it unwinds and cleans up
    }
}
static int lseek(int fd, int offset, int whence) {
    (void)fd; (void)whence; serviceDuringIo(1); return failSeek ? -1 : offset;
}
static int write(int fd, void *buf, int count) {
    (void)fd; (void)buf; (void)count; serviceDuringIo(2); writes++; return writeResult;
}
#define SEEK_SET 0
@FUNCTION@
@ABORT@
@STATUS@
int main(void) {
    char buffer[2048];
    writeResult = -5;
    assert(mc_writecluster(3, 0, buffer, 2) == -1 && tokens == 1);
    writeResult = 512;
    assert(mc_writecluster(3, 0, buffer, 2) == -1 && tokens == 1);
    writeResult = 2048;
    assert(mc_writecluster(3, 0, buffer, 2) == 0 && tokens == 1);
    genvmc_abort = 1;
    assert(mc_writecluster(3, 0, buffer, 2) == -2 && tokens == 1 && writes == 3);
    genvmc_abort = 0;
    assert(mc_writecluster(3, 0, buffer, 2) == 0 && tokens == 1);
    int previousWrites = writes;
    failSeek = 1;
    assert(mc_writecluster(3, 0, buffer, 2) == -1 && tokens == 1 && writes == previousWrites);
    failSeek = 0;
    assert(mc_writecluster(3, 0, buffer, 2) == 0 && tokens == 1);
    for (interruptIo = 1; interruptIo <= 2; interruptIo++) {
        genvmc_abort = 0;
        genvmc_stats.VMC_status = GENVMC_STAT_BUSY;
        assert(mc_writecluster(3, 0, buffer, 2) == 0 && genvmc_abort);
        int before = writes;
        assert(mc_writecluster(3, 1, buffer, 2) == -2 && writes == before);
    }
    return 0;
}
'''.replace("@FUNCTION@", function)
for marker, signature in (("@ABORT@", "static int vmc_abort("), ("@STATUS@", "static int vmc_status(")):
    first = source.index(signature)
    program = program.replace(marker, source[first:source.index('\n}', first) + 2])
with tempfile.TemporaryDirectory() as directory:
    cfile, exe = Path(directory) / "test.c", Path(directory) / "test"
    cfile.write_text(program, encoding="utf-8")
    subprocess.run(["gcc", "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-I"+str(root), str(cfile), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("genvmc: seek/write failure, retry and abort/status responsiveness during device IO pass")
