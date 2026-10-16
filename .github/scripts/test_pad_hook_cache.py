"""Execute actual PadOpen patching against low-address host fixture memory."""
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


pad = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "ee_core/src/padhook.c").read_text(encoding="utf-8")
util = (ROOT / "ee_core/src/util.c").read_text(encoding="utf-8")
prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
typedef unsigned int u32;
typedef unsigned char u8;
#include "ee_core/include/padpatterns.h"
#define NB_PADOPEN_PATTERN 7
#define IGR_LIBPAD 1
#define PADOPEN_HOOK 0
#define PADOPEN_CHECK 1
#define DPRINTF(...) ((void)0)
#define DBGCOL(...) ((void)0)
#define BGCOLND(...) ((void)0)
typedef struct {u32 *pattern,*mask;int size;unsigned short type,version;} pattern_t;
static struct {int libpad,libversion;} Pad_Data;
static void *scePadPortOpen, *scePad2CreateSocket;
static int EnableDebug, writes, flushes;
static int Hook_scePadPortOpen(void) {return 0;}
static int Hook_scePad2CreateSocket(void) {return 0;}
static void _sw(u32 value,u32 address) {*(u32 *)(uintptr_t)address=value;writes++;}
static void __attribute__((unused)) iFlushCache(int kind) {
 assert(writes>0);
 assert(kind==(flushes==0 ? 0 : 2));
 flushes++;
}
'''
test = r'''
int main(void) {
 const u32 base=0x100000, size=4096;
 u8 *memory=mmap((void *)(uintptr_t)base,size,PROT_READ|PROT_WRITE,
                 MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
 assert(memory!=(void *)-1 && (uintptr_t)memory==base);
 memset(memory,0,size);
 memcpy(memory+256,padPortOpenpattern0,sizeof(padPortOpenpattern0));
 u32 *call=(u32 *)(memory+64);
 *call=0x0c000000|((base+256)>>2);
 assert(Install_PadOpen_Hook(base,base+size,PADOPEN_HOOK)==1);
 assert(writes==1 && flushes==2);
 assert(*call==(0x0c000000|(((u32)(uintptr_t)Hook_scePadPortOpen>>2)&0x03ffffff)));
 assert(Pad_Data.libpad==1 && Pad_Data.libversion==0x211);
 /* Discovery alone does not patch or flush. */
 writes=flushes=0;
 assert(Install_PadOpen_Hook(base,base+size,PADOPEN_CHECK)==0);
 assert(writes==0 && flushes==0);
 /* Finding a library without an unpatched caller also does not flush. */
 assert(Install_PadOpen_Hook(base,base+size,PADOPEN_HOOK)==0);
 assert(writes==0 && flushes==0);
 memset(memory,0,size);
 assert(Install_PadOpen_Hook(base,base+size,PADOPEN_HOOK)==0);
 assert(writes==0 && flushes==0);
 /* A library ending exactly at the scan boundary is found without overread. */
 memcpy(memory+size-sizeof(padPortOpenpattern0),padPortOpenpattern0,sizeof(padPortOpenpattern0));
 *call=0x0c000000|((base+size-sizeof(padPortOpenpattern0))>>2);
 assert(Install_PadOpen_Hook(base,base+size,PADOPEN_HOOK)==1);
 assert(writes==1 && flushes==2);
 assert(munmap(memory,size)==0);
 puts("PASS: real PadOpen patch writes precede D/I flush; discovery and no-op scans do not flush");
}
'''
program = prefix + function(util, "u32 *find_pattern_with_mask(") + "\n" + function(pad, "int Install_PadOpen_Hook(") + test
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    source, exe = path / "test.c", path / "test"
    source.write_text(program, encoding="utf-8")
    (path / "tamtypes.h").write_text("/* Types supplied by host harness. */\n")
    subprocess.run(["gcc", "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                    "-Wno-pointer-to-int-cast", "-Wno-int-to-pointer-cast",
                    "-fsanitize=address,undefined", "-fno-pie", "-no-pie",
                    "-I", str(path), "-I", str(ROOT), str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
