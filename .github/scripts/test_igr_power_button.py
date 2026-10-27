"""Execute the IGR power-button sampler: one press is counted once (original #973).

The CDVD power-off status is latched hardware state. If the cancel takes more than a frame to clear
it, counting it every VBLANK turned a single press (power off) into a false double press (reset).
Also checks the IGR thread ignores a wakeup that carries no request, and the Fatal Fury default.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
padhook = (ROOT / 'ee_core/src/padhook.c').read_text()
start = padhook.index('        /* The CDVD power-off interrupt is a latched')
end = padhook.index('        ee_kmode_exit();', start)
sampler = padhook[start:end]

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
typedef unsigned char u8;
enum { IGR_COMBO_R3_L3 = 0x39, IGR_COMBO_START_SELECT = 0xF6 };
static volatile u8 ndin, poff, sdin, scmd;
#define CDVD_R_NDIN (&ndin)
#define CDVD_R_POFF (&poff)
#define CDVD_R_SCMD (&scmd)
#define CDVD_R_SDIN (&sdin)
static struct { int press, vb_count, latched; } Power_Button;
static struct { volatile u8 combo_type; } Pad_Data;
static int cancels;
static void frame(int pressed)
{
    ndin = pressed ? 0x20 : 0, poff = pressed ? 0x04 : 0, scmd = 0;
@SAMPLER@
    cancels += scmd == 0x1B;
}
static void reset(void) { Power_Button.press = Power_Button.vb_count = Power_Button.latched = 0; Pad_Data.combo_type = 0; cancels = 0; }
int main(void)
{
    int i;
    /* One press whose power-off status stays raised for several frames: power off, not reset. */
    for (i = 0; i < 5; i++)
        frame(1);
    for (i = 0; i < 60; i++)
        frame(0);
    assert(Power_Button.press == 1 && cancels == 1 && Pad_Data.combo_type == IGR_COMBO_R3_L3);
    /* Two real presses inside the window: reset. */
    reset();
    frame(1), frame(1), frame(0), frame(0), frame(1);
    for (i = 0; i < 60; i++)
        frame(0);
    assert(Power_Button.press == 2 && cancels == 2 && Pad_Data.combo_type == IGR_COMBO_START_SELECT);
    /* Further presses never overflow the count. */
    reset();
    for (i = 0; i < 10; i++)
        frame(i & 1);
    assert(Power_Button.press == 2);
    puts("PASS: a latched power-off status counts one press; double presses still reset");
    return 0;
}
'''

with tempfile.TemporaryDirectory() as tmp:
    src, exe = Path(tmp) / 'power.c', Path(tmp) / 'power'
    src.write_text(HARNESS.replace('@SAMPLER@', sampler))
    subprocess.run(['gcc', '-std=gnu99', '-Wall', '-Wextra', '-Werror', str(src), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)

thread = padhook[padhook.index('static void IGR_Thread('):]
assert re.search(r'while \(Pad_Data\.combo_type == 0x00\)\s+SleepThread\(\);', thread[:thread.index('DPRINTF')]), \
    'IGR thread must recheck the request after every wakeup'
assert 'volatile u8 combo_type;' in (ROOT / 'ee_core/include/padhook.h').read_text()
assert '"SLUS_217.23", COMPAT_MODE_6' in (ROOT / 'src/sources/supportbase.cpp').read_text()
print('PASS: IGR thread ignores stray wakeups; Fatal Fury BA2 defaults to Mode 6')
