"""Compile the production in-game RA event road on the host.

smap-ingame sets one RA datagram aside while the game owns SMAP RX
(ra_tap_notice / SMAPReadNotice), and ee_core's VBLANK handler acts on the
128-byte event raudp DMAs over: a pulse for an unlock, the IGR road for a
reset, nothing for a torn or repeated event.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
xfer = (root / 'modules/network/smap-ingame/xfer.c').read_text(encoding='utf-8')
overlay = (root / 'ee_core/src/ra_overlay.c').read_text(encoding='utf-8')

tap = xfer[xfer.index('/* Copy only achievement'):xfer.index('#endif', xfer.index('static void ra_tap_notice('))]
pulse = overlay[overlay.index('/* GS privileged registers'):overlay.rindex('#endif')]

program = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t u64;
#include "modules/network/common/ra_snap.h"
static int intr_depth, resets;
static void CpuSuspendIntr(int *state) { *state = intr_depth++; }
static void CpuResumeIntr(int state) { intr_depth = state; }
static u64 pmode_reg;
static unsigned bgcolor;
#define UNCACHED_SEG(x) (x)
#define BGCOLND(c) (bgcolor = (c))
static void IGR_RequestReset(void) { resets++; }
''' + tap.replace('(*(volatile u64 *)0x12000000)', 'pmode_reg') + pulse.replace(
    '#define GS_PMODE (*(volatile u64 *)0x12000000)', '#define GS_PMODE pmode_reg') + r'''

/* An Ethernet/IPv4/UDP frame to port 18195 carrying text. */
static unsigned frame(unsigned char *p, const char *text, unsigned port) {
    unsigned n = strlen(text), udp = 8 + n;
    memset(p, 0, 256);
    p[12] = 8; p[14] = 0x45; p[23] = 17;
    p[36] = port >> 8; p[37] = port & 255;
    p[38] = udp >> 8; p[39] = udp & 255;
    memcpy(p + 42, text, n);
    return 42 + n < 60 ? 60 : 42 + n;
}

static struct ra_event *ev;
static void post(unsigned kind, int torn) {
    ev->magic = RA_EVENT_MAGIC;
    ev->seq++;
    ev->kind = kind;
    ev->commit = torn ? ev->seq - 1 : ev->seq;
}

int main(void) {
    unsigned char p[256];
    char out[129];
    unsigned n;

    n = frame(p, "RAU1 42 10 Title", 18195);
    ra_tap_notice(p, n);
    assert(SMAPReadNotice(out, 8) == 0);                      /* too small: kept, not truncated */
    assert(SMAPReadNotice(out, 128) == 16 && !memcmp(out, "RAU1 42 10 Title", 16));
    assert(SMAPReadNotice(out, 128) == 0 && intr_depth == 0); /* handed out once */
    n = frame(p, "RAU1 42", 18196); ra_tap_notice(p, n); assert(SMAPReadNotice(out, 128) == 0);
    n = frame(p, "XXU1 42", 18195); ra_tap_notice(p, n); assert(SMAPReadNotice(out, 128) == 0);
    n = frame(p, "RAR1 ", 18195); ra_tap_notice(p, 46); assert(SMAPReadNotice(out, 128) == 0); /* truncated */
    n = frame(p, "RAU1 42 10 Title", 18195); ra_tap_notice(p, 42 + 15); assert(SMAPReadNotice(out, 128) == 0);
    n = frame(p, "RAR1 ", 18195); p[23] = 6; ra_tap_notice(p, n); assert(SMAPReadNotice(out, 128) == 0); /* TCP */
    n = frame(p, "RAR1 ", 18195); ra_tap_notice(p, n);
    n = frame(p, "RAU1 7", 18195); ra_tap_notice(p, n);       /* a second waits for the first to be read */
    assert(SMAPReadNotice(out, 128) == 5 && !memcmp(out, "RAR1 ", 5));
    {
        char longest[130];
        memset(longest, 'A', sizeof longest); longest[0] = 'R'; longest[128] = 0;
        n = frame(p, longest, 18195); ra_tap_notice(p, n); assert(SMAPReadNotice(out, 128) == 128);
        longest[128] = 'A'; longest[129] = 0;                  /* 129 bytes: more than the notice holds */
        n = frame(p, longest, 18195); ra_tap_notice(p, n); assert(SMAPReadNotice(out, 128) == 0);
    }
    puts("PASS: SMAP sets aside one whole RA datagram for port 18195, hands it out once, refuses the rest");

    ev = (struct ra_event *)RA_OverlayEventBuffer();
    RA_OverlayOnVblank(1);
    assert(!ra_ovl_running && !resets);
    post(RA_EVENT_MAKE_UNLOCK(25), 1);
    RA_OverlayOnVblank(2);
    assert(!ra_ovl_running);                                   /* commit not landed yet */
    ev->commit = ev->seq;
    RA_OverlayOnVblank(3);
    assert(ra_ovl_running && ra_ovl_start == 3);
    RA_OverlayOnVblank(4);
    assert(ra_ovl_start == 3);                                 /* the same event is one pulse */
    post(RA_EVENT_MAKE_UNLOCK(5), 1);
    RA_OverlayOnVblank(5);
    assert(ra_ovl_running && ra_ovl_start == 3 && pmode_reg != 0); /* a torn event does not stall the flash */
    ev->commit = ev->seq;
    RA_OverlayOnVblank(6);
    assert(ra_ovl_start == 6);
    for (unsigned f = 7; f < 6 + RA_OVL_DOWN + RA_OVL_UP + 1; f++)
        RA_OverlayOnVblank(f);
    assert(!ra_ovl_running && bgcolor == 0);
    post(RA_EVENT_RESET | 0x100, 0);                          /* kind's upper bits never hide a reset */
    RA_OverlayOnVblank(100);
    RA_OverlayOnVblank(101);
    assert(resets == 1 && !ra_ovl_running);
    post(7, 0);
    RA_OverlayOnVblank(102);
    assert(resets == 1 && !ra_ovl_running);
    ev = (struct ra_event *)RA_OverlayEventBuffer();           /* a new game starts from seq 0 again */
    post(RA_EVENT_UNLOCK, 0);
    RA_OverlayOnVblank(200);
    assert(ra_ovl_running && ra_ovl_start == 200);
    ev = (struct ra_event *)RA_OverlayEventBuffer();           /* and again: seq 1 is new for the next game */
    post(RA_EVENT_UNLOCK, 0);
    RA_OverlayOnVblank(300);
    assert(ra_ovl_start == 300);
    puts("PASS: VBLANK acts once per committed event: unlock pulses, reset to IGR, torn or unknown ignored");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='ra-ingame-events-') as temp:
    src, exe = Path(temp) / 'events.c', Path(temp) / 'events'
    src.write_text(program, encoding='utf-8')
    subprocess.run(['cc', '-std=gnu99', '-Wall', '-Werror', '-Wno-unused-function', '-Wno-unused-value',
                    '-fsanitize=address,undefined', '-I', str(root), str(src), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
