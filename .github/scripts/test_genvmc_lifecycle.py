"""Execute the real formatter request/worker/abort lifecycle with controlled scheduling."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'modules/vmc/genvmc/genvmc.c'
source = path.read_text(encoding='utf-8')
def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]

program = r'''
#include <assert.h>
#include <string.h>
#define DPRINTF(...) ((void)0)
#define TH_C 1
#define IOP_MUTEX_LOCKED 0
#include "modules/vmc/genvmc/genvmc.h"
static int genvmc_thread_sema=1, genvmc_abort_sema=2, genvmc_abort_finished_sema=-1;
static int genvmc_abort, tokens[4]={0,1,1,0}, failCreate, failStart, deleted, removed, formatResult;
static statusVMCparam_t genvmc_stats;
static createVMCparam_t genvmc_request;
typedef struct {int attr, option; void *thread; int stacksize, priority;} iop_thread_t;
static void *scheduled;
static char formatted[1024], erased[1024];
static int WaitSema(int id) {assert(id>0 && id<4 && tokens[id]==1); tokens[id]=0; return 0;}
static int SignalSema(int id) {assert(id>0 && id<4 && tokens[id]==0); tokens[id]=1; return 0;}
static int CreateThread(iop_thread_t *p) {(void)p;return failCreate ? -1 : 5;}
static int StartThread(int id, void *p) {assert(id==5);scheduled=p;return failStart ? -1 : 0;}
static int DeleteThread(int id) {assert(id==5);deleted++;return 0;}
static int CreateMutex(int state) {(void)state;return 3;}
static int DeleteSema(int id) {(void)id;return 0;}
static void ExitDeleteThread(void) {}
static int vmc_mcformat(char *name,int size,int block,int *progress,char *msg) {
    (void)size;(void)block;(void)progress;(void)msg;strcpy(formatted,name);
    return genvmc_abort ? -1000 : formatResult;
}
static int vmc_mccopy(char *name,int slot,int *progress,char *msg) {
    (void)slot;return vmc_mcformat(name,0,0,progress,msg);
}
static int remove(const char *name) {
    assert(genvmc_stats.VMC_status==GENVMC_STAT_BUSY);removed++;strcpy(erased,name);return 0;
}
@FUNCTIONS@
int main(void) {
    createVMCparam_t request={"mass0:/VMC/save_0.bin",8,16,15,-1};
    assert(vmc_create(&request)==0);
    assert(genvmc_stats.VMC_status==GENVMC_STAT_BUSY);
    assert(scheduled != &request);
    strcpy(request.VMC_filename,"mass0:/VMC/other.bin");
    assert(vmc_create(&request)<0); // no second job and no overwrite of the first request
    assert(vmc_abort()==0 && genvmc_abort);
    VMC_create_thread(scheduled);
    assert(!strcmp(formatted,"mass0:/VMC/save_0.bin"));
    assert(!strcmp(erased,formatted) && removed==1);
    assert(genvmc_stats.VMC_status==0 && genvmc_stats.VMC_error==-1000);
    assert(vmc_abort()==0); // abort after completion must not wait for a vanished worker
    assert(tokens[1]==1 && tokens[2]==1);
    failCreate=1; assert(vmc_create(&request)<0 && genvmc_stats.VMC_status==0);
    failCreate=0; failStart=1;
    assert(vmc_create(&request)<0 && deleted==1 && genvmc_stats.VMC_status==0);
    failStart=0;
    assert(vmc_create(&request)==0 && !genvmc_abort);
    VMC_create_thread(scheduled);
    assert(genvmc_stats.VMC_status==0 && genvmc_stats.VMC_error==0);
    assert(vmc_abort()==0 && removed==1); // a completed valid image is preserved
    formatResult=-7;
    assert(vmc_create(&request)==0); VMC_create_thread(scheduled);
    assert(genvmc_stats.VMC_status==0 && genvmc_stats.VMC_error==-7 && removed==1);
    return 0;
}
'''.replace('@FUNCTIONS@', '\n'.join(function(s) for s in (
    'static void VMC_create_thread(', 'static int vmc_create(', 'static int vmc_abort(')))
directory = root / 'build/test-tmp'
directory.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=directory) as temp:
    cfile, exe = Path(temp) / 'lifecycle.c', Path(temp) / 'lifecycle'
    cfile.write_text(program, encoding='utf-8')
    subprocess.run(['gcc', '-std=gnu99', '-Wall', '-Wextra', '-Wno-unused-function', '-Wno-unused-variable',
                    '-Werror', '-I'+str(root), str(cfile), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
print('genvmc: owned request, busy admission, pre-start/late abort, cleanup ordering and failed thread retry pass')
