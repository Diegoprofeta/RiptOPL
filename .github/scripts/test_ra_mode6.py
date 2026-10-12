"""Compile the production snapshot-only interrupt lifecycle, including retry."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
pad = (ROOT / "ee_core/src/padhook.c").read_text(encoding="utf-8")
start = pad.index("#ifdef RETROACHIEVEMENTS\n/* Compatibility Mode 6")
handlers = pad[start:pad.index("// Hook function for libpad", start)]
assert "#ifdef RETROACHIEVEMENTS\nstatic int RA_Intc_ID = -1;\n#endif" in pad
hooks = (ROOT / "ee_core/src/syshook.c").read_text(encoding="utf-8")
assert "if ((g_compat_mask & COMPAT_MODE_6) && ra_snap_iop != 0)" in hooks
# Client-triggered IGR is not implemented in this older private RA runtime.
# This port only adds snapshots; the broader RA migration remains in the parity ledger.
program = r'''
#include <assert.h>
#include <stdio.h>
#define kINTC_VBLANK_END 3
#ifdef RETROACHIEVEMENTS
static int RA_Intc_ID = -1;
static int registrations, enabled, frames, exits, fail;
static int (*callback)(int);
static int AddIntcHandler(int cause, int (*fn)(int), int next) {
    assert(cause == kINTC_VBLANK_END && next == 0);
    registrations++;
    if (fail) return -1;
    callback = fn; return 7;
}
static void EnableIntc(int cause) { assert(cause == kINTC_VBLANK_END); enabled++; }
static void RA_OnVblank(void) { frames++; }
static void ExitHandler(void) { exits++; }
#endif
@HANDLERS@
int main(void) {
#ifdef RETROACHIEVEMENTS
    fail = 1; Install_RA_Vblank();
    assert(registrations == 1 && !enabled && RA_Intc_ID == -1 && !callback);
    fail = 0; Install_RA_Vblank(); Install_RA_Vblank();
    assert(registrations == 2 && enabled == 1 && RA_Intc_ID == 7);
    assert(callback(3) == 0 && frames == 1 && exits == 1);
#endif
    puts("PASS: Mode 6 snapshot handler is RA-only, retryable and idempotent");
}
'''.replace("@HANDLERS@", handlers)
with tempfile.TemporaryDirectory() as directory:
    src = Path(directory) / "mode6.c"
    exe = Path(directory) / "mode6"
    src.write_text(program, encoding="utf-8")
    for defines in ([], ["-DRETROACHIEVEMENTS"]):
        subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        *defines, str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)
