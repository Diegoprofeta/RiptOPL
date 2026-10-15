"""Execute pad publication/invalidation and VBLANK reads across IOP reset."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "ee_core/src/padhook.c").read_text(encoding="utf-8")


def function(signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


# Stop before physical-button registers and teardown; execute the actual input
# reads in interrupt context, rather than substituting upstream's polling worker.
handler = function("static int IGR_Intc_Handler(")
handler = handler[:handler.index("#ifdef RETROACHIEVEMENTS", handler.index("if (Pad_Data.pad_buf"))]
handler = handler.replace("    int i;", "    (void)cause;")
handler += "    return Pad_Data.combo_type;\n}\n"
prefix = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char u8;
typedef unsigned short u16;
#define IGR_LIBPAD 1
#define IGR_LIBPAD2 2
#define IGR_PAD_STABLE_V1 6
#define IGR_PAD_STABLE_V2 1
#define IGR_COMBO_R1_L1_R2_L2 0xf0
#define IGR_COMBO_START_SELECT 0xf6
#define IGR_COMBO_R3_L3 0xf9
#define USE_LOCAL_EECORE_CONFIG
#define kINTC_VBLANK_END 3
static int intrEnabled = 1, reads;
static int DI(void) { int previous=intrEnabled;intrEnabled=0;return previous; }
static void EI(void) { intrEnabled=1; }
static void *uncached(void *p) { assert(!intrEnabled);reads++;return p; }
#define UNCACHED_SEG(p) uncached(p)
static struct { u16 libpad,libversion;u8 *pad_buf;int vb_count;
 int pos_combo1,pos_combo2,pos_state,pos_frame;u8 combo_type,prev_frame; } Pad_Data;
static struct { int press,vb_count; } Power_Button;
static int IGR_Thread_ID=-1, IGR_Intc_ID=-1, padOpen_hooked;
static int creates, starts, handlers, enables, snapshots;
static int _gp;
static u8 IGR_Stack[4096];
#define IGR_STACK_SIZE sizeof(IGR_Stack)
typedef struct { void *gp_reg;void (*func)(void *);void *stack;
 unsigned stack_size;int initial_priority; } ee_thread_t;
static void IGR_Thread(void *p) {(void)p;}
static int CreateThread(ee_thread_t *p) {assert(p->func==IGR_Thread);creates++;return 5;}
static void StartThread(int id,void *p) {assert(id==5 && !p);starts++;}
static int AddIntcHandler(int cause,int (*fn)(int),int n) {
 assert(cause==kINTC_VBLANK_END && fn && !n);handlers++;return 7;
}
static void EnableIntc(int n) {assert(n==kINTC_VBLANK_END);enables++;}
#ifdef RETROACHIEVEMENTS
static void RA_OnVblank(void) {snapshots++;}
#endif
'''
test = r'''
static int tick(void) {
 int previous=intrEnabled;intrEnabled=0;
 int result=IGR_Intc_Handler(0);
 assert(!intrEnabled);intrEnabled=previous;return result;
}
int main(void) {
 u8 old[128]={0}, fresh[128]={0};
 Install_IGR();assert(creates==1 && starts==1 && handlers==1 && enables==1);
 Pad_Data.libpad=IGR_LIBPAD;Pad_Data.libversion=0x160;
 Set_libpad_Params(old);assert(intrEnabled && Pad_Data.pos_state==112);
 old[112]=IGR_PAD_STABLE_V1;old[3]=IGR_COMBO_R1_L1_R2_L2;
 old[2]=IGR_COMBO_START_SELECT;
 Pad_Data.vb_count=7;Pad_Data.prev_frame=44;padOpen_hooked=1;
 Invalidate_PadBuffer();assert(intrEnabled && !Pad_Data.pad_buf && !padOpen_hooked);
 assert(!Pad_Data.vb_count && !Pad_Data.prev_frame);
 assert(tick()==0 && reads==0); /* reused old memory looks like a reset combo */
 Power_Button.press=1;Power_Button.vb_count=17;Pad_Data.combo_type=IGR_COMBO_START_SELECT;
 intrEnabled=0;Invalidate_PadBuffer();Install_IGR();
 assert(!intrEnabled && Pad_Data.combo_type==IGR_COMBO_START_SELECT);
 assert(Power_Button.press==1 && Power_Button.vb_count==17);
 assert(creates==1 && starts==1 && handlers==1 && enables==1);
 Pad_Data.vb_count=9;Pad_Data.prev_frame=99;
 Set_libpad_Params(fresh);
 assert(!intrEnabled && !Pad_Data.vb_count && !Pad_Data.prev_frame && Pad_Data.pad_buf==fresh);
 Pad_Data.combo_type=0;assert(tick()==0 && reads==4 && !intrEnabled);
 fresh[112]=IGR_PAD_STABLE_V1;fresh[3]=IGR_COMBO_R1_L1_R2_L2;
 fresh[2]=IGR_COMBO_START_SELECT;
 assert(tick()==IGR_COMBO_START_SELECT && !intrEnabled);
 intrEnabled=1;Invalidate_PadBuffer();assert(intrEnabled);
 Set_libpad_Params(fresh);assert(intrEnabled);
 /* All supported layout variants restart liveness and publish consistent offsets. */
 Pad_Data.libversion=0x150;Set_libpad_Params(fresh);
 assert(Pad_Data.pos_state==4 && Pad_Data.pos_frame==0 && Pad_Data.pos_combo1==11);
 Pad_Data.libpad=IGR_LIBPAD2;Set_libpad_Params(fresh);
 assert(Pad_Data.pos_state==4 && Pad_Data.pos_frame==124 && Pad_Data.pos_combo1==29);
 memset(fresh,0,sizeof(fresh));Pad_Data.combo_type=0;
 fresh[4]=IGR_PAD_STABLE_V2;fresh[29]=IGR_COMBO_R1_L1_R2_L2;fresh[28]=IGR_COMBO_START_SELECT;
 assert(tick()==IGR_COMBO_START_SELECT && intrEnabled);
#ifdef RETROACHIEVEMENTS
 assert(snapshots==4);
#else
 assert(snapshots==0);
#endif
 puts("PASS: stale pad refusal, reopen layouts, interrupt state and pending reset/power preservation");
}
'''
program = prefix + handler + "\n".join(function(sig) for sig in (
    "void Invalidate_PadBuffer(", "static void Set_libpad_Params(", "void Install_IGR(")) + test
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    c = path / "test.c"
    c.write_text(program, encoding="utf-8")
    for defines in ([], ["-DRETROACHIEVEMENTS"]):
        exe = path / "test"
        subprocess.run(["gcc", "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-pie", "-no-pie",
                        *defines, str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)
