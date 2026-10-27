"""RA IOP modules: thread startup, POPS startup ownership and raw ARP, compiled from the production sources.

Ported from the RA sections of the original's test_pr894_hardening. rapops is adapted to RiptOPL's
config blob: the loader packs the modules into g_cfg.blob, so a bad offset or size must refuse.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]


def read(path):
    return (root / path).read_text(encoding="utf-8")


def function(source, signature):
    start = source.index(signature)
    depth = 0
    for index in range(source.index("{", start), len(source)):
        depth += {"{": 1, "}": -1}.get(source[index], 0)
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError(signature)


def run(name, program):
    with tempfile.TemporaryDirectory(prefix="ra-start-") as tmp:
        src, exe = Path(tmp) / (name + ".c"), Path(tmp) / name
        src.write_text(program, encoding="utf-8")
        subprocess.run(["cc", "-std=gnu99", "-Wall", "-Werror", "-Wno-pointer-to-int-cast",
                        "-Wno-int-to-pointer-cast", "-I", str(root), str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


for module, worker, registered in (("raudp", "ra_thread", True), ("rapull", "rp_thread", False)):
    start = function(read(f"modules/network/{module}/{module}.c"), "int _start(")
    tail = start[start.index("    thread.attr = TH_C;"):]
    run(module + "_thread", r'''
#include <assert.h>
#include <stdio.h>
#define TH_C 1
#define MODULE_NO_RESIDENT_END 1
#define MODULE_RESIDENT_END 0
typedef struct { int attr,option,stacksize,priority; void (*thread)(void*); } iop_thread_t;
static int create_fail,start_fail,deleted,started;
static void WORKER(void *p) { (void)p; }
static int CreateThread(iop_thread_t *t) { (void)t;return create_fail?-1:7; }
static int StartThread(int id,void *p) { (void)p;assert(id==7);started++;return start_fail?-1:0; }
static void DeleteThread(int id) { assert(id==7);deleted++; }
'''.replace("WORKER", worker) + (r'''
static int _exp_raudp,register_fail,released;
static int RegisterLibraryEntries(int *p) { (void)p;return register_fail?-1:0; }
static void ReleaseLibraryEntries(int *p) { (void)p;released++; }
''' if registered else "") + "static int launch(void) { iop_thread_t thread;int tid;\n" + tail + r'''
int main(void) {
    create_fail=1;assert(launch()==1 && !deleted && !started);
    create_fail=0;start_fail=1;assert(launch()==1 && deleted==1 && started==1);
    start_fail=0;assert(launch()==0 && deleted==1 && started==2);
''' + (r'''
    assert(released==1);register_fail=1;
    assert(launch()==1 && deleted==2 && started==2 && released==1);
''' if registered else "") + f'    puts("PASS: {module} thread startup failure releases dormant thread and exports");\n}}\n')

rapops = re.sub(r"^#include.*$", "", read("modules/network/rapops/rapops.c"), flags=re.M)
run("rapops_start", r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "modules/network/common/ra_snap.h"
#include "modules/network/common/rapops_cfg.h"
typedef uint32_t u32;
typedef unsigned char u8;
#define IRX_ID(a,b,c)
#define MODULE_RESIDENT_END 0
#define MODULE_NO_RESIDENT_END 1
#define ALLOC_FIRST 0
#define _start rapops_start
extern struct rapops_cfg g_cfg;
static void *owned[4];
static int allocated,freed,fail_module=-1,fail_alloc=-1,sender_flags,started[RAPOPS_BLOBS],start_error;
static size_t snap_size;
static void *AllocSysMemory(int a,size_t n,void *p) {
    (void)a;(void)p;if(allocated==fail_alloc)return NULL;
    if(!allocated)snap_size=n;
    return owned[allocated++]=malloc(n);
}
static void FreeSysMemory(void *p) {
    for(int i=0;i<allocated;i++)if(owned[i]==p){free(p);owned[i]=NULL;freed++;return;}
    assert(0);
}
static int LoadModuleBuffer(void *p) {
    for(int i=0;i<RAPOPS_BLOBS;i++)if(p==&g_cfg.blob[g_cfg.blob_off[i]])return i;
    assert(0);return -1;
}
static int StartModule(int id,const char *name,int n,const char *args,int *result) {
    (void)name;(void)n;started[id]++;
    if(id==RAPOPS_RAUDP)sender_flags=args[RA_ARG_RX]-'0';
    if(start_error && id==fail_module)return -1;
    *result=id==fail_module ? MODULE_NO_RESIDENT_END : MODULE_RESIDENT_END;
    return 0;
}
''' + rapops + r'''
static void reset(void) {
    for(int i=0;i<allocated;i++)free(owned[i]);
    memset(owned,0,sizeof(owned));memset(started,0,sizeof(started));
    allocated=freed=start_error=0;fail_module=fail_alloc=-1;
    g_cfg.ipcfg_len=3;g_cfg.count=1;g_cfg.bytes=4;g_cfg.node_count=0;
    for(int i=0;i<RAPOPS_BLOBS;i++){g_cfg.blob_off[i]=i*16;g_cfg.blob_size[i]=16;}
}
static int stopped_before_sender(void) {
    return !allocated && !started[RAPOPS_SMAP] && !started[RAPOPS_RAUDP] && !started[RAPOPS_RAPULL];
}
int main(void) {
    for(int mode=0;mode<2;mode++)for(int pin=0;pin<2;pin++) {
        reset();g_cfg.client_mode=mode;g_cfg.host_pinned=pin;
        assert(rapops_start(0,NULL)==MODULE_NO_RESIDENT_END);
        assert(sender_flags==1+mode*2+pin*4 && started[RAPOPS_RAPULL]==1);
        assert(snap_size==RA_SNAP_TOTAL_FOR(4) && snap_size<RA_SNAP_TOTAL);
    }
    /* DEV9 may already be POPS's own; its failure is tolerated. */
    reset();fail_module=RAPOPS_DEV9;rapops_start(0,NULL);assert(started[RAPOPS_RAPULL]==1);
    for(int id=RAPOPS_SMSUTILS;id<=RAPOPS_SMAP;id++) {
        reset();fail_module=id;rapops_start(0,NULL);assert(!allocated && !started[RAPOPS_RAUDP]);
    }
    reset();fail_module=RAPOPS_RAUDP;rapops_start(0,NULL);assert(allocated==1 && freed==1 && !started[RAPOPS_RAPULL]);
    reset();fail_module=RAPOPS_RAPULL;rapops_start(0,NULL);assert(allocated==2 && freed==1 && owned[0]!=NULL);
    reset();fail_alloc=0;rapops_start(0,NULL);assert(!started[RAPOPS_RAUDP]);
    reset();fail_alloc=1;rapops_start(0,NULL);assert(started[RAPOPS_RAUDP] && !started[RAPOPS_RAPULL]);
    reset();fail_module=RAPOPS_RAUDP;start_error=1;rapops_start(0,NULL);assert(freed==1 && !started[RAPOPS_RAPULL]);
    /* A module the loader did not pack, misaligned, past the blob or wrapping refuses before loading. */
    reset();g_cfg.blob_size[RAPOPS_SMSTCPIP]=0;rapops_start(0,NULL);assert(stopped_before_sender() && started[RAPOPS_SMSUTILS] && !started[RAPOPS_SMSTCPIP]);
    reset();g_cfg.blob_off[RAPOPS_SMSUTILS]=8;rapops_start(0,NULL);assert(stopped_before_sender());
    reset();g_cfg.blob_off[RAPOPS_SMAP]=RAPOPS_BLOB_BYTES-16;g_cfg.blob_size[RAPOPS_SMAP]=32;
    rapops_start(0,NULL);assert(stopped_before_sender());
    reset();g_cfg.blob_off[RAPOPS_SMSUTILS]=0xFFFFFFF0u;g_cfg.blob_size[RAPOPS_SMSUTILS]=32;
    rapops_start(0,NULL);assert(stopped_before_sender());
    reset();g_cfg.blob_size[RAPOPS_RAPULL]=0;rapops_start(0,NULL);
    assert(started[RAPOPS_RAUDP] && !started[RAPOPS_RAPULL] && allocated==2 && freed==1 && owned[0]!=NULL);
    /* A config the loader did not write starts nothing. */
    reset();g_cfg.count=0;assert(rapops_start(0,NULL)==MODULE_NO_RESIDENT_END && !started[RAPOPS_DEV9]);
    reset();g_cfg.bytes=0;rapops_start(0,NULL);assert(!started[RAPOPS_DEV9]);
    reset();puts("PASS: POPS pinned ABI, proportional allocation, dependency/sender/reader failure ownership, blob bounds");
}
''')

run("arp", r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef unsigned int u32;
typedef unsigned char u8;
#define USE_SMAP_EMAC3_REGS
#define SMAP_R_EMAC3_ADDR_HI 0
#define SMAP_R_EMAC3_ADDR_LO 1
#define SMAP_EMAC3_GET32(x) ((x)==0 ? 0x0011U : 0x22334455U)
static u32 ra_src_ip=0x0200000a;
static int busy,sent;
static u8 packet[60];
static int ra_tx_busy(void) { return busy; }
static int SMAPSendPacket(void *p,int n) { assert(n==60);memcpy(packet,p,n);sent++;return 0; }
''' + function(read("modules/network/raudp/raudp.c"), "static int ra_request_mac(") + r'''
int main(void) {
    busy=1;assert(!ra_request_mac(0x0700000a) && !sent);
    busy=0;assert(ra_request_mac(0x0700000a) && sent==1);
    for(int i=0;i<6;i++)assert(packet[i]==255 && packet[32+i]==0);
    const u8 mac[]={0,0x11,0x22,0x33,0x44,0x55};
    assert(!memcmp(packet+6,mac,6) && !memcmp(packet+22,mac,6));
    assert(packet[12]==8 && packet[13]==6 && packet[15]==1 && packet[16]==8);
    assert(packet[18]==6 && packet[19]==4 && packet[21]==1);
    const u8 src[]={10,0,0,2},dst[]={10,0,0,7};
    assert(!memcmp(packet+28,src,4) && !memcmp(packet+38,dst,4));
    puts("PASS: raw ARP requests use correct addresses and yield to busy game TX");
}
''')
