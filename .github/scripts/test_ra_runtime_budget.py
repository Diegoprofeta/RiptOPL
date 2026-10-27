"""Actual EE-core setup/sampling/pacing and C++ watch parser at expanded bounds."""
from pathlib import Path
import subprocess
import tempfile
import sys

root = Path(__file__).resolve().parents[2]
core = (root / 'ee_core/src/ra.c').read_text(encoding='utf-8')
core_functions = Path(sys.argv[1]).read_text(encoding='utf-8') if len(sys.argv)>1 else core
watch = (root / 'src/sources/rawatch.cpp').read_text(encoding='utf-8')


def function(source, signature):
    first = source.index(signature)
    return source[first:source.index('\n}', first) + 2]


def run(name, program):
    with tempfile.TemporaryDirectory() as temp:
        cpp, exe = Path(temp)/(name+'.cpp'), Path(temp)/name
        (Path(temp)/'osd_config.h').write_text('typedef struct {unsigned int unused;} ConfigParam;\n')
        cpp.write_text(program, encoding='utf-8')
        subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-sign-compare','-Wno-int-to-pointer-cast',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=undefined',
                        '-I',temp,'-I',str(root),str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)


prefix = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <algorithm>
typedef uint8_t u8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef uint64_t u64;
#define RETROACHIEVEMENTS
#include "modules/network/common/ra_snap.h"
'''
state = core[core.index('static u8 *ra_snap_buf'):core.index('#define RA_RAM_HIGH')]
state += '#define RA_RAM_HIGH 0x02000000\n'
# COP0 Count has no host equivalent: each read advances a fake clock by 7.
state = state.replace(function(state, 'static inline u32 ra_ticks'), 'static u32 ticks;\nstatic u32 ra_ticks(void) { return ticks += 7; }')
run('ee_ra_budget', prefix + r'''
#include "ee_core/include/coreconfig.h"
struct EECoreConfig_t g_ee_core_config;
static u8 gameRam[0x02000000];
static void *uncached(uintptr_t address) {return address<sizeof(gameRam) ? gameRam+address : (void*)address;}
#define UNCACHED_SEG(address) uncached((uintptr_t)(address))
#define RA_START_DELAY 600
#define RA_PROBE 0
unsigned int ra_snap_iop=0x1000;
typedef struct {void *src,*dest;int size,attr;} SifDmaTransfer_t;
static int transfers, overlays, dmaBusy;
static int isceSifDmaStat(int) {return dmaBusy ? 0 : -1;}
static int isceSifSetDma(SifDmaTransfer_t *dma,int count) {
    assert(count==1 && dma->size>0 && dma->size<=RA_SNAP_TOTAL && dma->size%16==0);
    const ra_snap *snap=(const ra_snap*)dma->src;
    assert(snap->bytes<=RA_SNAP_MAX_BYTES);
    assert(*(u32*)((u8*)dma->src+RA_SNAP_TRAILER_OFF(snap->bytes))==snap->seq);
    transfers++;return transfers;
}
static void RA_OverlayOnVblank(unsigned) {overlays++;}
''' + state + '\n' + '\n'.join(function(core_functions,s) for s in
    ('int RA_SnapBytes(', 'void RA_SetupWatchList(', 'static void ra_snap_send(', 'void RA_OnVblank(')) + r'''
static u8 work[RA_EE_WORK_BYTES(RA_WATCH_MAX,RA_NODE_MAX)+128] __attribute__((aligned(64)));
static u32 entries[RA_WATCH_MAX];
static ra_node nodes[RA_NODE_MAX];
static void setup(int count,int bytes,int chains=0) {
    memset(work,0xCC,sizeof(work));g_ee_core_config={};
    auto &cfg=g_ee_core_config;
    cfg.raWatchList=entries;cfg.raWatchCount=count;cfg.raSnapBytes=bytes;
    cfg.raNodeList=chains ? nodes : nullptr;cfg.raNodeCount=chains;
    cfg.raWorkArea=work;cfg.raWorkBytes=RA_EE_WORK_BYTES(count,chains);
    strcpy(cfg.GameID,"SLUS_123.45");
    transfers=overlays=dmaBusy=0;ra_frames=ra_snap_dma_id=ra_snap_seq=0;
    RA_SetupWatchList();
}
static void tailUnchanged(unsigned start) {for(unsigned i=start;i<sizeof(work);i++)assert(work[i]==0xCC);}
int main() {
    assert(RA_WATCH_MAX==4096 && RA_SNAP_PARTS==9);
    for(int parts=1;parts<=9;parts++) {
        int bytes=((parts-1)*RA_SNAP_CHUNK_BYTES/4+1)*4;
        int count=bytes/4;
        for(int i=0;i<count;i++)entries[i]=RA_WATCH_PACK(0x80000+4*i,4);
        setup(count,bytes);assert(ra_watch_count==count && ra_snap_bytes==bytes && RA_SnapBytes()==bytes);
        assert(ra_snap_every==(unsigned)(parts+2)/3);
        for(int frame=0;frame<1200;frame++)RA_OnVblank();
        assert(overlays==1200 && transfers==600/(int)ra_snap_every);
        tailUnchanged(g_ee_core_config.raWorkBytes);
    }
    // Full entry/node budgets, with source + scratch words beyond 4096.
    int bytes=0;
    for(int i=0;i<RA_WATCH_MAX;i++) {
        int size=i<2136 ? 4 : i==2136 ? 2 : 1;
        entries[i]=RA_WATCH_PACK(0x80000+4*i,size);bytes+=size;
    }
    for(int i=0;i<RA_NODE_MAX;i++)nodes[i]={RA_NODE_PACK(0,0,4),(u32)i*4};
    u32 base=0x100000;memcpy(gameRam+0x80000,&base,4);
    for(int i=0;i<RA_NODE_MAX;i++){u32 v=0x12340000+i;memcpy(gameRam+base+i*4,&v,4);}
    setup(RA_WATCH_MAX,bytes,RA_NODE_MAX);
    assert(ra_watch_count==4096 && ra_node_count==128 && ra_snap_bytes==RA_SNAP_MAX_BYTES && ra_snap_every==3);
    ra_snap_send();assert(transfers==1 && RA_SnapBytes()==RA_SNAP_MAX_BYTES);
    // The read cost is two clock reads apart; the frame is the gap between two VBLANKs.
    RA_OnVblank();RA_OnVblank();ra_snap_dma_id=0;ra_snap_send();
    assert(((const ra_snap*)work)->read_cycles==7 && ((const ra_snap*)work)->frame_cycles==7);
    const u8 *vals=work+RA_SNAP_HDR;
    for(int i=0;i<RA_NODE_MAX;i++) {
        u32 address,value;memcpy(&address,vals+bytes+i*8,4);memcpy(&value,vals+bytes+i*8+4,4);
        assert(address==base+(u32)i*4 && value==0x12340000+(u32)i);
    }
    tailUnchanged(g_ee_core_config.raWorkBytes);
    // Undersized or unaligned reservations refuse without writing into them.
    setup(1,4);g_ee_core_config.raWorkBytes--;memset(work,0xCC,sizeof(work));RA_SetupWatchList();
    assert(!ra_watch_count && !RA_SnapBytes());tailUnchanged(0);
    setup(1,4);g_ee_core_config.raWorkArea=work+1;memset(work,0xCC,sizeof(work));RA_SetupWatchList();
    assert(!ra_watch_count);tailUnchanged(0);
    setup(1,4);g_ee_core_config.raSnapBytes=3;memset(work,0xCC,sizeof(work));RA_SetupWatchList();
    assert(!ra_watch_count);tailUnchanged(0);
    // Wider direct reads at odd addresses must use byte loads.
    entries[0]=RA_WATCH_PACK(0x80001,4);entries[1]=RA_WATCH_PACK(0x80009,2);
    for(int i=0;i<16;i++)gameRam[0x80000+i]=(u8)i;
    setup(2,6);ra_snap_send();assert(!memcmp(work+RA_SNAP_HDR,gameRam+0x80001,4));
    assert(!memcmp(work+RA_SNAP_HDR+4,gameRam+0x80009,2));
    // Unreadable addresses produce zeros without disturbing snapshot shape.
    entries[0]=RA_WATCH_PACK(0x7ffff,4);entries[1]=RA_WATCH_PACK(0x1ffffff,2);
    setup(2,6);ra_snap_send();for(int i=0;i<6;i++)assert(work[RA_SNAP_HDR+i]==0);
    puts("PASS: EE module-storage bounds, full entries/nodes, IRQ reads and one/two/three-frame pacing");
}
''')

run('loader_ra_budget', prefix + r'''
#include "include/rawatch.h"
#define LOG(...) ((void)0)
static std::vector<u32> disk;
static unsigned readPosition;
static int fake_open(const char*,int) {readPosition=0;return 3;}
static int fake_read(int,void *out,int len) {
    len=std::min<unsigned>(len,disk.size()*4-readPosition);
    memcpy(out,(u8*)disk.data()+readPosition,len);readPosition+=len;return len;
}
static int fake_close(int) {return 0;}
#define open fake_open
#define read fake_read
#define close fake_close
#define O_RDONLY 0
''' + '\n'.join(function(watch,s) for s in
    ('void RaWatch::clearWatchList(', 'void RaWatch::takeNodes(', 'int RaWatch::setWatchList(', 'int RaWatch::loadWatchList(')) + r'''
int main() {
    RaWatch watch;
    std::vector<u32> blob(4+RA_WATCH_MAX+2+RA_NODE_MAX*2);
    auto *header=(ra_watch_file*)blob.data();
    *header={RA_WATCH_MAGIC,RA_WATCH_VERSION,RA_WATCH_MAX,RA_WATCH_MAX};
    for(int i=0;i<RA_WATCH_MAX;i++)blob[4+i]=RA_WATCH_PACK(0x80000+i,1);
    auto *nf=(ra_node_file*)&blob[4+RA_WATCH_MAX];*nf={RA_NODE_MAGIC,RA_NODE_MAX};
    auto *node=(ra_node*)(nf+1);for(int i=0;i<RA_NODE_MAX;i++)node[i]={RA_NODE_PACK(0,0,1),0};
    int len=blob.size()*4;
    assert(watch.setWatchList(blob.data(),len,"SLUS_123.45")==4096 && watch.nodeCount()==128);
    assert(len<20*1024);
    disk=blob;watch.clearWatchList();
    assert(watch.loadWatchList("save.wl","SLUS_123.45")==4096 && watch.nodeCount()==128);
    for(int bad : {0,3,5,15}) {
        blob[4]=RA_WATCH_PACK(0x80000,bad);
        assert(watch.setWatchList(blob.data(),len,"SLUS_123.45")<0 && !watch.watchCount());
        disk=blob;assert(watch.loadWatchList("save.wl","SLUS_123.45")<0 && !watch.watchCount());
    }
    blob[4]=RA_WATCH_PACK(0x80000,1);header->bytes++;
    assert(watch.setWatchList(blob.data(),len,"SLUS_123.45")<0 && !watch.watchCount());
    disk=blob;assert(watch.loadWatchList("save.wl","SLUS_123.45")<0 && !watch.watchCount());
    header->bytes--;nf->count=0xffffffff;
    assert(watch.setWatchList(blob.data(),len,"SLUS_123.45")==4096 && !watch.nodeCount());
    assert(watch.setWatchList(blob.data(),16+4096*4-1,"SLUS_123.45")<0);
    puts("PASS: real C++ parser accepts large sets and refuses invalid widths/byte sums/truncation");
}
''')

app=(root/'src/app/host.cpp').read_text(encoding='utf-8')
first=app.index('unsigned int raWorkBytes() override')
method=app[first:app.index('\n    }',first)+6]
run('launch_ra_capacity', prefix + r'''
static unsigned int entries[RA_WATCH_MAX];
static int count,bytes,nodes,gRATelemetry=1;
unsigned int *GetWatchList() {return entries;}
int GetWatchCount() {return count;}
int GetWatchBytes() {return bytes;}
int GetNodeCount() {return nodes;}
struct LaunchServices {virtual unsigned int raWorkBytes()=0;};
class OplLaunch final:public LaunchServices {public:
''' + method + r'''
};
int main() {
    for(int i=0;i<RA_WATCH_MAX;i++)entries[i]=RA_WATCH_PACK(0x80000+i,1);
    OplLaunch launch;
    for(int n : {0,1,1024,4096,4097}) {
        count=bytes=n;nodes=0;
        assert(launch.raWorkBytes()==(n>0 && n<=4096 ? (unsigned)RA_EE_WORK_BYTES(n,0) : 0));
    }
    count=bytes=4096;nodes=128;
    assert(launch.raWorkBytes()==RA_EE_WORK_BYTES(4096,128));
    nodes=-1;assert(!launch.raWorkBytes());nodes=129;assert(!launch.raWorkBytes());
    nodes=0;bytes--;assert(!launch.raWorkBytes());bytes++;
    entries[0]=RA_WATCH_PACK(0x80000,3);assert(!launch.raWorkBytes());
    entries[0]=RA_WATCH_PACK(0x80000,1);gRATelemetry=0;assert(!launch.raWorkBytes());
    puts("PASS: actual C++ launch service reserves only validated set-sized module storage");
}
''')
