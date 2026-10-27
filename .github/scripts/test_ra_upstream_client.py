"""RA: the production console header builder, parsed by xeRAbora's unmodified alpha.16 client.

Ported from the original's test_ra_ps1 upstream_client case. The fixture is pinned; see its README.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]


def run(name, program):
    with tempfile.TemporaryDirectory(prefix="ra-upstream-") as tmp:
        src, exe = Path(tmp) / (name + ".c"), Path(tmp) / name
        src.write_text(program, encoding="utf-8")
        subprocess.run(["cc", "-std=gnu99", "-Wall", "-Werror", "-I", str(root), str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


fixture = root/'.github/scripts/fixtures/xerabora-alpha16'
sender = (root/'modules/network/raudp/raudp.c').read_text()
sender = sender[sender.index('struct ra_field\n'):sender.index('/* ---- Formatting helpers')]
parser = re.sub(r'^#include.*$', '', (fixture/'snapshot.c').read_text(), flags=re.M)
run('upstream_client', r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include ".github/scripts/fixtures/xerabora-alpha16/ra_snap.h"
#include ".github/scripts/fixtures/xerabora-alpha16/snapshot.h"
typedef unsigned char u8;
typedef unsigned int u32;
#define RA_PAYLOAD 1472
static u8 ra_payload[RA_PAYLOAD];
static char ra_game_id[16]="P123456789abcde";
static unsigned char values[RA_SNAP_MAX_BYTES];
static int have, nodes;
static unsigned char *watchlist_values(void) {return values;}
static int watchlist_count(void) {return 1;}
static int watchlist_bytes(void) {return 4;}
static int watchlist_snapshot_bytes(void) {return 12;}
static void watchlist_set_have_nodes(int v) {nodes=v;}
static void watchlist_set_have_values(int v) {have=v;}
''' + sender + parser + r'''
static void field(int id,unsigned int value) {
    for(int i=ra_fields[id].width-1;i>=0;i--) {
        ra_payload[RA_OFF(id)+i]='0'+value%10;value/=10;
    }
}
int main(void) {
    char serial[16];
    ra_head_build();
    assert(ra_chunk==RA_SNAP_CHUNK_BYTES);
    assert(snapshot_serial((char*)ra_payload,serial,sizeof(serial)));
    assert(!strcmp(serial,ra_game_id));
    field(RA_F_N,1);field(RA_F_VB,4);field(RA_F_NP,1);field(RA_F_SQ,1);
    memcpy(ra_payload+ra_head_len,"\x11\x22\x33\x44",4);
    snapshot_reset();
    assert(snapshot_feed((char*)ra_payload,ra_head_len+4)==1);
    assert(have && !nodes && !memcmp(values,"\x11\x22\x33\x44",4));
    assert(snapshot_feed((char*)ra_payload,ra_head_len+4)==0);
    field(RA_F_SQ,2);field(RA_F_VB,12);
    memset(ra_payload+ra_head_len,0x55,12);
    assert(snapshot_feed((char*)ra_payload,ra_head_len+12)==1 && nodes);
    field(RA_F_SQ,3);field(RA_F_N,2);
    assert(snapshot_feed((char*)ra_payload,ra_head_len+12)==0 && snapshot_stale());
    puts("PASS: production sender accepted by upstream alpha.16 parser; serial, direct values, pointer nodes, duplicates and stale lists");
}
''')
