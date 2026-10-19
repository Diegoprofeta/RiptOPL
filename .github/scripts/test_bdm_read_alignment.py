#!/usr/bin/env python3
"""Exercise actual BDM sector reads with a driver requiring word-aligned buffers.

An optional source path permits the same regression against the pre-port body.
All image data is synthetic; this does not emulate DMA or console execution.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "modules/iopcore/cdvdman/device-bdm.c"
source = path.read_text(encoding="utf-8")
start = source.index("int DeviceReadSectors(")
function = source[start:source.index("\n}", start) + 2]
program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char u8;
typedef uint32_t u32;
typedef uint64_t u64;
enum { SCECdErNO, SCECdErTRMOPN, SCECdErREAD };
struct block_device { int unused; };
static struct block_device device, *g_bd;
static struct {
    struct { unsigned int frag_count, frag_start; } fragfile[1];
    int frags[4];
} cdvdman_settings;
static int bdm_io_sema = 9, locked, waits, signals, calls, fail_call;
static unsigned int fail_result;
static u64 expected_lsn, next_sector;
static unsigned int remaining;
static int aligned_request;
static void *destination;
static u8 storage[2048 * 3 + 128] __attribute__((aligned(64)));

static void WaitSema(int id) {
    assert(id == bdm_io_sema && !locked);
    locked = 1; waits++;
}
static void SignalSema(int id) {
    assert(id == bdm_io_sema && locked);
    locked = 0; signals++;
}
static u8 pattern(u64 sector, unsigned int byte) {
    return (u8)(sector * 17 + byte * 3);
}
static unsigned int bd_defrag(struct block_device *bd, unsigned int count, int *frags,
                             u64 sector, void *buffer, unsigned int sectors) {
    assert(locked && bd == &device && count == 2 && frags == &cdvdman_settings.frags[1]);
    assert(((uintptr_t)buffer & 3) == 0); /* Model a word/DMA-aligned block driver. */
    assert(sector == next_sector);
    if (aligned_request) {
        assert(calls == 0 && buffer == destination && sectors == remaining);
    } else {
        assert(((uintptr_t)buffer & 63) == 0 && sectors == 4 && remaining >= 4);
    }
    calls++;
    unsigned int result = calls == fail_call ? fail_result : sectors;
    assert(result <= sectors);
    for (unsigned int n = 0; n < result * 512; n++)
        ((u8 *)buffer)[n] = pattern(sector + n / 512, n % 512);
    next_sector += sectors;
    remaining -= sectors;
    return result;
}
@FUNCTION@
static void prepare(int offset, unsigned int sectors) {
    assert(!locked);
    memset(storage, 0xcc, sizeof(storage));
    g_bd = &device;
    cdvdman_settings.fragfile[0].frag_start = 1;
    cdvdman_settings.fragfile[0].frag_count = 2;
    destination = storage + 64 + offset;
    aligned_request = offset == 0;
    expected_lsn = (1ULL << 34) + 7;
    next_sector = expected_lsn * 4;
    remaining = sectors * 4;
    waits = signals = calls = fail_call = 0;
    fail_result = 0;
}
static void verify(unsigned int copied, unsigned int total) {
    unsigned int offset = (u8 *)destination - storage;
    for (unsigned int n = 0; n < sizeof(storage); n++) {
        u8 expected = 0xcc;
        if (n >= offset && n < offset + copied * 2048) {
            unsigned int byte = n - offset;
            expected = pattern(expected_lsn * 4 + byte / 512, byte % 512);
        }
        assert(storage[n] == expected); /* Includes untouched failed sectors and both guards. */
    }
    assert(offset + total * 2048 < sizeof(storage));
    assert(!locked && waits == 1 && signals == 1);
}
int main(void) {
    for (int offset = 0; offset < 4; offset++) {
        for (unsigned int sectors = 1; sectors <= 3; sectors++) {
            prepare(offset, sectors);
            assert(DeviceReadSectors(expected_lsn, destination, sectors) == SCECdErNO);
            assert(calls == (offset ? (int)sectors : 1) && remaining == 0);
            verify(sectors, sectors);
        }
    }
    /* Every failed bounce read may partially write its private buffer, never the destination. */
    for (int offset = 1; offset < 4; offset++) {
        for (int failure = 1; failure <= 3; failure++) {
            for (unsigned int partial = 0; partial < 4; partial += 3) {
                prepare(offset, 3); fail_call = failure; fail_result = partial;
                assert(DeviceReadSectors(expected_lsn, destination, 3) == SCECdErREAD);
                assert(calls == failure);
                verify(failure - 1, 3);
            }
        }
    }
    /* Preserve the direct aligned path's existing partial-read error behavior. */
    prepare(0, 3); fail_call = 1;
    assert(DeviceReadSectors(expected_lsn, destination, 3) == SCECdErREAD);
    assert(calls == 1); verify(0, 3);
    prepare(0, 3); fail_call = 1; fail_result = 4;
    assert(DeviceReadSectors(expected_lsn, destination, 3) == SCECdErREAD);
    assert(calls == 1); verify(1, 3);
    for (int offset = 0; offset < 4; offset++) {
        prepare(offset, 1); g_bd = NULL;
        assert(DeviceReadSectors(expected_lsn, destination, 1) == SCECdErTRMOPN);
        assert(!calls && !waits && !signals && !locked);
        for (unsigned int n = 0; n < sizeof(storage); n++) assert(storage[n] == 0xcc);
        prepare(offset, 0);
        assert(DeviceReadSectors(expected_lsn, destination, 0) == SCECdErNO);
        assert(calls == (offset ? 0 : 1)); verify(0, 0);
    }
    puts("PASS: BDM offsets 0-3, multi-sector data, guards, fast path, failures, detached device and semaphore balance");
    return 0;
}
'''.replace("@FUNCTION@", function)

with tempfile.TemporaryDirectory() as temp:
    src = Path(temp) / "bdm_read.c"
    exe = Path(temp) / ("bdm_read.exe" if os.name == "nt" else "bdm_read")
    src.write_text(program, encoding="utf-8")
    sanitizers = ["-fsanitize=address,undefined", "-fno-pie", "-no-pie"] if os.name != "nt" else []
    # The target's u32 pointer cast tests only low alignment bits; host pointers can be 64-bit.
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-pointer-to-int-cast", *sanitizers, str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
