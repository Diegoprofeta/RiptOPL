"""Production PS1 hashing (VCD and HDL) against host fixtures. Ported from the original's
test_ra_ps1.py; the hashing it covers cannot validate PS2 drive or IOP behavior."""
from pathlib import Path
import hashlib
import os
import re
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='ra-ps1-') as directory:
    tmp = Path(directory)

    def run(name, source, extra=()):
        cxx = 'constexpr' in source
        path = tmp / (name + ('.cpp' if cxx else '.c'))
        exe = tmp / (name + '.exe')
        source = '#ifdef _WIN32\n#include <direct.h>\n#define mkdir(path, mode) _mkdir(path)\n#endif\n' + source
        path.write_text(source, encoding='utf-8')
        objs = []
        for i, e in enumerate(map(str, extra)):
            o = str(tmp / ('%s_x%d.o' % (name, i)))
            subprocess.run(['gcc', '-std=gnu99', '-Wall', '-Wextra', '-Werror', '-I', str(root), '-c', e, '-o', o], check=True)
            objs.append(o)
        compiler = ['g++', '-std=gnu++17'] if cxx else ['gcc', '-std=gnu99']
        subprocess.run(compiler + ['-Wall', '-Wextra', '-Werror', '-I', str(root), str(path), *objs, '-o', str(exe)], check=True)
        subprocess.run([str(exe)], cwd=tmp, check=True)

    payload = bytearray((i % 251 for i in range(2048 * 3 + 17)))
    payload[:8] = b'PS-X EXE'
    struct.pack_into('<I', payload, 28, len(payload) - 2048)

    def record(name, lba, size):
        result = bytearray(34 + len(name))
        result[0] = len(result)
        struct.pack_into('<I', result, 2, lba)
        struct.pack_into('<I', result, 10, size)
        result[32] = len(name)
        result[33:33 + len(name)] = name.encode()
        return result

    def fixture(name, boot='SLUS_012.15', cnf=True, fallback=False, overflow=False, listed=None):
        iso = bytearray(40 * 2048)
        iso[16*2048+1:16*2048+6] = b'CD001'
        struct.pack_into('<II', iso, 16*2048+158, 20, 0)
        struct.pack_into('<I', iso, 16*2048+166, 2048)
        entries = b''
        if cnf:
            text = ('BOOT = cdrom:\\' + boot + ';1\r\n').encode()
            iso[22*2048:22*2048+len(text)] = text
            entries += record('SYSTEM.CNF;1', 22, len(text))
        if '\\' in boot:
            entries += record('D;1', 21, 2048)
            nested = record('G.EXE;1', 24, len(payload))
            iso[21*2048:21*2048+len(nested)] = nested
        else:
            entries += record(('PSX.EXE' if fallback else listed or boot) + ';1', 24, len(payload))
        iso[20*2048:20*2048+len(entries)] = entries
        data = bytearray(payload)
        if overflow:
            struct.pack_into('<I', data, 28, 0xfffff800)
        iso[24*2048:24*2048+len(data)] = data
        raw = bytearray(0x100000 + 40 * 2352)
        for lba in range(40):
            at = 0x100000 + lba * 2352 + 24
            raw[at:at+2048] = iso[lba*2048:(lba+1)*2048]
        (tmp / name).write_bytes(raw)

    fixture('retail.vcd')
    fixture('nested.vcd', 'D\\G.EXE')
    fixture('fallback.vcd', cnf=False, fallback=True)
    fixture('overflow.vcd', overflow=True)
    # rcheevos compares names without case: SYSTEM.CNF may name the executable in lower case.
    fixture('lower.vcd', 'slus_012.15', listed='SLUS_012.15')
    # Split a synthetic HDL game's logical ISO across two separated ATA
    # extents. Its real 1024-byte map lives at the APA game start sector.
    # No partition table or real HDD is opened or modified by this test.
    raw = (tmp / 'retail.vcd').read_bytes()
    hdisk = bytearray(1150 * 512)
    for logical in range(40):
        physical = (200 + 4 * logical) if logical < 16 else (1024 + 4 * (logical - 16))
        at = 0x100000 + logical * 2352 + 24
        hdisk[physical * 512:physical * 512 + 2048] = raw[at:at + 2048]
    hdisk[100 * 512 + 172:100 * 512 + 172 + len(b'SLUS_012.15')] = b'SLUS_012.15'
    struct.pack_into('<i', hdisk, 100 * 512 + 240, 2)
    struct.pack_into('<III', hdisk, 100 * 512 + 244, 0, 200, 16 * 2048)
    struct.pack_into('<III', hdisk, 100 * 512 + 256, 16, 1024, 24 * 2048)
    (tmp / 'hdd.raw').write_bytes(hdisk)
    (tmp / 'truncated.vcd').write_bytes((tmp / 'retail.vcd').read_bytes()[:0x100000+26*2352])
    source = re.sub(r'^#include.*$', '', (root/'src/sources/rahash.cpp').read_text(), flags=re.M)
    prefix = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <stdlib.h>
#endif
#include "include/md5.h"
#include "include/hdl_layout.h"
typedef void (*ra_step_fn)(const char *);
static unsigned max_hdd_sectors;
static int hddReadSectors(unsigned int lba,unsigned int n,void *out) {
    FILE *f=fopen("hdd.raw","rb");int ok=0;
    if(n>max_hdd_sectors)max_hdd_sectors=n;
    if(!f)return -1;
    if(!fseek(f,(long)lba*512,SEEK_SET) && fread(out,512,n,f)==n)ok=1;
    fclose(f);
    return ok?0:-1;
}
typedef struct { unsigned char trycount, spindlctrl, datapattern, pad; } sceCdRMode;
enum { SCECdErNO=0, SCECdSecS2048=0, SCECdSpinNom=1, SCECdSpinStm=2 };
#define LOG(...) ((void)0)
#define lseek64 lseek
static int sceCdDiskReady(int m) {(void)m;return 0;}
static int sceCdRead(unsigned a,unsigned b,void *c,sceCdRMode *d) {(void)a;(void)b;(void)c;(void)d;return 0;}
static int sceCdSync(int m) {(void)m;return 0;}
static int sceCdGetError(void) {return 0;}
'''
    checks = '''
int main(void) {
#ifdef _WIN32
    _set_fmode(_O_BINARY);
#endif
    char boot[16], hash[33], key[16], key2[16];
'''
    for file, boot in [('retail.vcd', 'SLUS_012.15'), ('nested.vcd', 'D\\G.EXE'), ('fallback.vcd', 'PSX.EXE'), ('lower.vcd', 'slus_012.15')]:
        expected = hashlib.md5(boot.encode() + payload).hexdigest()
        escaped = boot.replace('\\', '\\\\')
        checks += f'assert(raHashVcd("{file}",boot,sizeof(boot),hash)==0);\n'
        checks += f'assert(!strcmp(boot,"{escaped}") && !strcmp(hash,"{expected}"));\n'
        checks += f'assert(raVcdBootName("{file}",boot,sizeof(boot))==0 && !strcmp(boot,"{escaped}"));\n'
    checks += r'''
    assert(raHashVcd("truncated.vcd",boot,sizeof(boot),hash)<0 && hash[0]==0);
    assert(raHashVcd("overflow.vcd",boot,sizeof(boot),hash)<0 && hash[0]==0);
    assert(raHashVcd("missing.vcd",boot,sizeof(boot),hash)<0 && hash[0]==0);
    assert(raVcdWatchKey("mass0:/POPS/First.VCD",key,sizeof(key))==0);
    assert(strlen(key)==15 && key[0]=='P');
    assert(raVcdWatchKey("mass0:/POPS/Second.VCD",key2,sizeof(key2))==0);
    assert(strcmp(key,key2)!=0); /* Both images can contain the same BOOT. */
    assert(raVcdWatchKey("MASS0:\\POPS\\FIRST.vcd",key2,sizeof(key2))==0);
    assert(!strcmp(key,key2)); /* Case and separator folding for FAT roots. */
    assert(raVcdWatchKey("mass1:/POPS/First.VCD",key2,sizeof(key2))==0);
    assert(strcmp(key,key2)!=0); /* A second simultaneously mounted USB. */
    assert(raVcdWatchKey("mass0:/POPS/First.VCD",key2,15)<0);
    assert(raVcdWatchKey("",key2,sizeof(key2))<0);
    /* A watch list's path key is not proof that its contents are unchanged. */
    assert(raVcdWatchGuardMatches("",key,hash)==0); /* Old pre-guard list. */
    assert(raVcdWatchGuardStore("",key,"bad")<0);
    assert(raHashVcd("retail.vcd",boot,sizeof(boot),hash)==0);
    assert(raVcdWatchGuardStore("",key,hash)<0); /* RA directory absent. */
    assert(mkdir("RA",0777)==0);
    assert(raVcdWatchGuardStore("",key,hash)==0);
    assert(raVcdWatchGuardMatches("",key,hash)==1);
    hash[0] = hash[0]=='a' ? 'b':'a';
    assert(raVcdWatchGuardMatches("",key,hash)==0); /* Different content. */
    assert(raHashVcd("retail.vcd",boot,sizeof(boot),hash)==0);
    FILE *guard=fopen("RA/P", "rb");
    assert(!guard); /* Only keyed sidecar is created. */
    assert(raVcdWatchGuardMatches("",key,hash)==1);
    assert(raVcdWatchGuardStore("","Pbad",hash)<0); /* bad key input */
    /* HDL read-only hashing crosses separated APA extents and shares the
       ISO content hash; corrupt partition counts/overlaps must fail closed. */
    assert(raHashHdl(100,"SLUS_012.15",hash)==0);
    assert(max_hdd_sectors>4 && max_hdd_sectors<=16); /* Bounded, batched raw reads. */
    assert(raHashHdl(100,"SLES_999.99",hash)<0 && !hash[0]); /* Stale list. */
    assert(raHashHdl(100,"SLUS_012.15",hash)==0);
    assert(!strcmp(hash,"''' + hashlib.md5(b"SLUS_012.15" + payload).hexdigest() + r'''"));
    FILE *disk=fopen("hdd.raw","r+b"); assert(disk);
    int bad_count=66;
    assert(!fseek(disk,100*512+240,SEEK_SET));
    assert(fwrite(&bad_count,4,1,disk)==1);
    fclose(disk);
    assert(raHashHdl(100,"SLUS_012.15",hash)<0 && !hash[0]);
    disk=fopen("hdd.raw","r+b");assert(disk);
    bad_count=2;
    assert(!fseek(disk,100*512+240,SEEK_SET));
    assert(fwrite(&bad_count,4,1,disk)==1);
    int overlap=10;
    assert(!fseek(disk,100*512+256,SEEK_SET));
    assert(fwrite(&overlap,4,1,disk)==1);
    fclose(disk);
    assert(raHashHdl(100,"SLUS_012.15",hash)<0 && !hash[0]);
    puts("PASS: HDL two-extent read-only hash, bounded partition count and overlap rejection");
    puts("PASS: PS1 hashes and stale-VCD guard, missing, mismatched and malformed sidecars");
}
'''
    run('hash_ps1', prefix + source + checks, [root/'src/platform/md5.c'])

