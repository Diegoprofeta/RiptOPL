#!/usr/bin/env python3
"""Regression tests for SIO2MAN v1/v2 hook compatibility in mcemu and pademu."""

from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MCEMU_C = ROOT / "modules" / "mcemu" / "mcemu.c"
MCEMU_SYS_C = ROOT / "modules" / "mcemu" / "mcemu_sys.c"
PADEMU_C = ROOT / "modules" / "pademu" / "pademu.c"
PADEMU_SYS_C = ROOT / "modules" / "pademu" / "sys_utils.c"
IOPMGR_C = ROOT / "ee_core" / "src" / "iopmgr.c"
SYSTEM_C = ROOT / "src" / "platform" / "system.cpp"


def extract_function(text: str, signature: str) -> str:
    search_from = 0
    while True:
        start = text.find(signature, search_from)
        if start < 0:
            raise RuntimeError(f"Could not find function definition: {signature}")

        brace = text.find("{", start)
        semi = text.find(";", start)
        if brace < 0:
            raise RuntimeError(f"Could not find opening brace for: {signature}")
        if 0 <= semi < brace:
            search_from = semi + 1
            continue

        depth = 0
        for idx in range(brace, len(text)):
            ch = text[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]

        raise RuntimeError(f"Could not find closing brace for: {signature}")


def check_static_wiring() -> None:
    iopmgr_text = IOPMGR_C.read_text(encoding="utf-8")
    system_text = SYSTEM_C.read_text(encoding="utf-8")
    mcemu_text = MCEMU_C.read_text(encoding="utf-8")
    pademu_text = PADEMU_C.read_text(encoding="utf-8")

    reset_fn = extract_function(iopmgr_text, "int ResetIopSpecial(")
    new_reset_fn = extract_function(iopmgr_text, "int New_Reset_Iop(")
    sio2_idx = reset_fn.find("LoadOPLModule(OPL_MODULE_ID_SIO2MAN")
    switch_idx = reset_fn.find("switch (config->GameMode)")
    reset_call_idx = new_reset_fn.find("ResetIopSpecial(")
    vmc_idx = new_reset_fn.find("LoadOPLModule(OPL_MODULE_ID_MCEMU")
    pademu_idx = new_reset_fn.find("LoadOPLModule(OPL_MODULE_ID_PADEMU")
    if not (0 <= sio2_idx < switch_idx and 0 <= reset_call_idx < vmc_idx < pademu_idx):
        raise AssertionError("ResetIopSpecial must preload OPL_MODULE_ID_SIO2MAN before GameMode switch, VMC, and PADEMU")

    if "if (sio2manLoaded > 0)" not in reset_fn:
        raise AssertionError("ResetIopSpecial must gate OPL_MODULE_ID_MX4SIOBD on sio2manLoaded > 0")

    if "if (!(modules & CORE_IRX_MMCE) && ((modules & (CORE_IRX_MX4SIO | CORE_IRX_VMC)) PADEMU_ARG))" not in system_text:
        raise AssertionError("system.cpp must pack OPL_MODULE_ID_SIO2MAN for non-MMCE MX4SIO, VMC, or PADEMU launches")

    for label, text in (("mcemu.c", mcemu_text), ("pademu.c", pademu_text)):
        if 'GetExportTable("sio2man", 0x100)' not in text or 'GetExportTable("sio2man", 0x200)' not in text:
            raise AssertionError(f"{label} must inspect both 0x100 (v1) and 0x200 (v2) sio2man export tables")


HARNESS_C = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;

typedef struct _Sio2Packet {
    u32 iostatus;
    u32 data1[4];
    u32 data2[4];
    u32 data3;
    u32 ctrl[16];
    u32 data4;
    u32 pwr_len;
    u32 prd_len;
    void *pwr_buf;
    void *prd_buf;
    void *wrmaddr;
    u32 wrwords;
    u32 wrcount;
    void *rdmaddr;
    u32 rdwords;
    u32 rdcount;
} Sio2Packet;

typedef struct {
    u16 PageSize;
    u16 BlockSize;
    u32 CardSize;
} McSpec;

typedef struct _MemoryCard {
    int mcnum;
    int rpage;
    int rdoff;
    int wpage;
    int wroff;
    u8 *dbufp;
    u8 *cbufp;
    int rcoff;
    int wcoff;
    int tcode;
    McSpec cspec;
    int flags;
} MemoryCard;

typedef void (*Sio2McProc)(Sio2Packet *arg);
typedef void (*Sio2McProc2)(void);

#define MCEMU_PORTS 2
#define DPRINTF(...) do {} while (0)

static int g_irq_depth = 0;
static void CpuSuspendIntr(int *oldstate) {
    *oldstate = g_irq_depth++;
}
static void CpuResumeIntr(int oldstate) {
    g_irq_depth = oldstate;
}

static void mips_memcpy(void *dst, const void *src, u32 size) {
    memcpy(dst, src, size);
}
static void mips_memset(void *dst, int c, u32 size) {
    memset(dst, c, size);
}

static MemoryCard memcards[MCEMU_PORTS];
static Sio2McProc pSio2man25[2], pSio2man51[2];
static Sio2McProc2 psio2_mc_transfer_init[2], psio2_transfer_reset[2];
static void (*pSio2man67)(void);
static int sio2TransferVersion = 0;

static u32 g_stat6c_check = 0;
static u32 *hookSio2man67(void) {
    if (pSio2man67)
        pSio2man67();
    return &g_stat6c_check;
}

static void SioResponse(MemoryCard *mcd, void *buf, int length) {
    if (length >= 2) {
        memset(buf, 0xFF, (size_t)(length - 2));
        ((u8 *)buf)[length - 2] = 0x2B;
        ((u8 *)buf)[length - 1] = (u8)mcd->tcode;
    }
}
static int GetInt(void *ptr) {
    u8 *p = (u8 *)ptr;
    return p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24);
}
static u32 CalculateEDC(u8 *buf, u32 size) {
    u32 x = 0;
    for (u32 i = 0; i < size; i++)
        x ^= buf[i];
    return x & 0xFF;
}
static int MceEraseBlock(MemoryCard *mcd, int page) { (void)mcd; (void)page; return 1; }
static int MceStartRead(MemoryCard *mcd, int page) { (void)mcd; (void)page; return 1; }
static int MceStartWrite(MemoryCard *mcd, int page) { (void)mcd; (void)page; return 1; }
static int MceRead(MemoryCard *mcd, void *buf, u32 size) { (void)mcd; memset(buf, 0, size); return 1; }
static int MceWrite(MemoryCard *mcd, void *buf, u32 size) { (void)mcd; (void)buf; (void)size; return 1; }

void Sio2McEmu(Sio2Packet *sd, int ver);
void hookSio2man(Sio2Packet *sd, Sio2McProc sio2proc, int ver);
void InstallSio2manHook(void *exp, int ver);

static void hookSio2McInit_1(void);
static void hookSio2McInit_2(void);
static void hookSio2man25_1(Sio2Packet *sd);
static void hookSio2man25_2(Sio2Packet *sd);
static void hookSio2man51_1(Sio2Packet *sd);
static void hookSio2man51_2(Sio2Packet *sd);
static void Sio2McEmu_1(Sio2Packet *sd);
static void Sio2McEmu_2(Sio2Packet *sd);
static void sio2McUnlock(int ver);
static void sio2McLock(int ver);

__MCEMU_SYS_FUNCS__
__MCEMU_FUNCS__

typedef Sio2Packet sio2_transfer_data_t;
static Sio2McProc pademu_pSio2man25[2], pademu_pSio2man51[2];

static void pademu_hookSio2man(sio2_transfer_data_t *td, Sio2McProc sio2proc) {
    sio2proc(td);
}

#define pSio2man25 pademu_pSio2man25
#define pSio2man51 pademu_pSio2man51
#define InstallSio2manHook pademu_InstallSio2manHook
#define hookSio2man25_1 pademu_hookSio2man25_1
#define hookSio2man25_2 pademu_hookSio2man25_2
#define hookSio2man51_1 pademu_hookSio2man51_1
#define hookSio2man51_2 pademu_hookSio2man51_2

static void hookSio2man25_1(sio2_transfer_data_t *sd);
static void hookSio2man25_2(sio2_transfer_data_t *sd);
static void hookSio2man51_1(sio2_transfer_data_t *sd);
static void hookSio2man51_2(sio2_transfer_data_t *sd);
void InstallSio2manHook(void *exp, int ver);

__PADEMU_FUNCS__

#undef pSio2man25
#undef pSio2man51
#undef InstallSio2manHook
#undef hookSio2man25_1
#undef hookSio2man25_2
#undef hookSio2man51_1
#undef hookSio2man51_2

static int g_v1_init_calls = 0, g_v2_init_calls = 0;
static int g_v1_reset_calls = 0, g_v2_reset_calls = 0;
static int g_v1_25_calls = 0, g_v1_49_calls = 0;
static int g_v2_25_calls = 0, g_v2_51_calls = 0;
static int g_v2_67_calls = 0;

static void orig_v1_init(void) { g_v1_init_calls++; }
static void orig_v2_init(void) { g_v2_init_calls++; }
static void orig_v1_reset(void) { g_v1_reset_calls++; }
static void orig_v2_reset(void) { g_v2_reset_calls++; }
static void orig_v1_25(Sio2Packet *sd) { (void)sd; g_v1_25_calls++; }
static void orig_v1_49(Sio2Packet *sd) { (void)sd; g_v1_49_calls++; }
static void orig_v2_25(Sio2Packet *sd) { (void)sd; g_v2_25_calls++; }
static void orig_v2_51(Sio2Packet *sd) { (void)sd; g_v2_51_calls++; }
static void orig_v2_67(void) { g_v2_67_calls++; }
static void dummy_entry(void) {}

static void init_table(void **table, size_t count) {
    for (size_t i = 0; i < count; i++)
        table[i] = (void *)dummy_entry;
    table[count] = NULL;
}

int main(void) {
    void *v1_exp[56];
    void *v2_exp[72];

    init_table(v1_exp, 52);
    init_table(v2_exp, 70);

    /* Alias entry 24 and 28 (mc_transfer_init / pad_transfer_init), and alias 25/49 in v1 */
    v1_exp[24] = (void *)orig_v1_init;
    v1_exp[28] = (void *)orig_v1_init;
    v1_exp[25] = (void *)orig_v1_25;
    v1_exp[26] = (void *)orig_v1_reset;
    v1_exp[49] = (void *)orig_v1_49;

    v2_exp[24] = (void *)orig_v2_init;
    v2_exp[28] = (void *)orig_v2_init;
    v2_exp[25] = (void *)orig_v2_25;
    v2_exp[26] = (void *)orig_v2_reset;
    v2_exp[51] = (void *)orig_v2_51;
    v2_exp[67] = (void *)orig_v2_67;

    memcards[0].mcnum = 0;
    memcards[0].tcode = 0x55;
    memcards[1].mcnum = -1;

    /* Install both v1 and v2 hooks, then reinstall to verify idempotence */
    InstallSio2manHook(v1_exp, 0);
    InstallSio2manHook(v2_exp, 1);
    InstallSio2manHook(v1_exp, 0);
    InstallSio2manHook(v2_exp, 1);

    assert(psio2_mc_transfer_init[0] == orig_v1_init);
    assert(psio2_mc_transfer_init[1] == orig_v2_init);
    assert(psio2_transfer_reset[0] == orig_v1_reset);
    assert(psio2_transfer_reset[1] == orig_v2_reset);
    assert(pSio2man25[0] == orig_v1_25);
    assert(pSio2man25[1] == orig_v2_25);
    assert(pSio2man51[0] == orig_v1_49);
    assert(pSio2man51[1] == orig_v2_51);
    assert(pSio2man67 == orig_v2_67);

    /* Alias slot #28 must also be hooked to the matching init wrapper */
    assert(v1_exp[24] == v1_exp[28]);
    assert(v2_exp[24] == v2_exp[28]);

    /* Calling v1 init wrapper should set sio2TransferVersion = 0 and call orig_v1_init */
    ((Sio2McProc2)v2_exp[24])();
    assert(sio2TransferVersion == 1 && g_v2_init_calls == 1);
    ((Sio2McProc2)v1_exp[28])();
    assert(sio2TransferVersion == 0 && g_v1_init_calls == 1);

    /* Non-VMC command on port 0 should pass through to the matching version's original handler */
    u8 cmd_pad[4] = {0x01, 0x42, 0x00, 0x00};
    u8 rx_buf[16] = {0};
    Sio2Packet pkt;
    memset(&pkt, 0, sizeof(pkt));
    pkt.ctrl[0] = 0x40; /* PIO mode, port 0 */
    pkt.pwr_buf = cmd_pad;
    pkt.prd_buf = rx_buf;

    ((Sio2McProc)v1_exp[25])(&pkt);
    assert(g_v1_25_calls == 1 && g_v2_25_calls == 0);
    ((Sio2McProc)v2_exp[25])(&pkt);
    assert(g_v1_25_calls == 1 && g_v2_25_calls == 1);
    ((Sio2McProc)v1_exp[49])(&pkt);
    assert(g_v1_49_calls == 1 && g_v2_51_calls == 0);
    ((Sio2McProc)v2_exp[51])(&pkt);
    assert(g_v1_49_calls == 1 && g_v2_51_calls == 1);

    /* VMC command (0x81) via v1 entry #25 must unlock/lock v1, not v2 */
    u8 cmd_mc[4] = {0x81, 0x11, 0x00, 0x00};
    memset(&pkt, 0, sizeof(pkt));
    pkt.ctrl[0] = (4u << 18) | 0x70; /* DMA mode, port 0, length 4 */
    pkt.wrmaddr = cmd_mc;
    pkt.rdmaddr = rx_buf;
    pkt.wrwords = 1;
    pkt.rdwords = 1;
    pkt.wrcount = 1;
    pkt.rdcount = 1;

    g_v1_init_calls = g_v2_init_calls = 0;
    g_v1_reset_calls = g_v2_reset_calls = 0;
    ((Sio2McProc)v1_exp[25])(&pkt);
    assert(g_v1_reset_calls == 1 && g_v1_init_calls == 1);
    assert(g_v2_reset_calls == 0 && g_v2_init_calls == 0);
    assert(pkt.iostatus == 0x1100);

    /* VMC command (0x81) via v2 entry #51 must unlock/lock v2, not v1 */
    g_v1_init_calls = g_v2_init_calls = 0;
    g_v1_reset_calls = g_v2_reset_calls = 0;
    ((Sio2McProc)v2_exp[51])(&pkt);
    assert(g_v2_reset_calls == 1 && g_v2_init_calls == 1);
    assert(g_v1_reset_calls == 0 && g_v1_init_calls == 0);
    assert(pkt.iostatus == 0x1100);

    /* Verify ROM sio2man case where entry 25 and 49 alias the same function */
    void *rom_v1_exp[56];
    init_table(rom_v1_exp, 52);
    rom_v1_exp[24] = (void *)orig_v1_init;
    rom_v1_exp[25] = (void *)orig_v1_25;
    rom_v1_exp[26] = (void *)orig_v1_reset;
    rom_v1_exp[49] = (void *)orig_v1_25; /* aliased to 25 */
    pademu_InstallSio2manHook(rom_v1_exp, 0);
    pademu_InstallSio2manHook(rom_v1_exp, 0);
    assert(pademu_pSio2man25[0] == orig_v1_25);

    printf("PASS: SIO2MAN v1/v2 hooks preserve separate callbacks and lock/unlock state\n");
    return 0;
}
"""


def run_host_harness() -> None:
    mcemu_sys_text = MCEMU_SYS_C.read_text(encoding="utf-8")
    pademu_sys_text = PADEMU_SYS_C.read_text(encoding="utf-8")
    mcemu_text = MCEMU_C.read_text(encoding="utf-8")
    pademu_text = PADEMU_C.read_text(encoding="utf-8")

    # Ensure mcemu_sys.c and pademu/sys_utils.c have identical HookExportEntry bodies
    hook_mcemu = extract_function(mcemu_sys_text, "void *HookExportEntry(")
    hook_pademu = extract_function(pademu_sys_text, "void *HookExportEntry(")
    if hook_mcemu != hook_pademu:
        raise AssertionError("HookExportEntry in mcemu_sys.c and pademu/sys_utils.c must stay identical")

    mcemu_sys_funcs = "\n\n".join(
        [
            extract_function(mcemu_sys_text, "u32 GetExportTableSize("),
            extract_function(mcemu_sys_text, "void *GetExportEntry("),
            hook_mcemu,
        ]
    )

    mcemu_funcs = "\n\n".join(
        [
            extract_function(mcemu_text, "void InstallSio2manHook("),
            extract_function(mcemu_text, "static void hookSio2McInit_1("),
            extract_function(mcemu_text, "static void hookSio2McInit_2("),
            extract_function(mcemu_text, "static void hookSio2man25_1("),
            extract_function(mcemu_text, "static void hookSio2man25_2("),
            extract_function(mcemu_text, "static void hookSio2man51_1("),
            extract_function(mcemu_text, "static void hookSio2man51_2("),
            extract_function(mcemu_text, "static void Sio2McEmu_1("),
            extract_function(mcemu_text, "static void Sio2McEmu_2("),
            extract_function(mcemu_text, "static void sio2McUnlock("),
            extract_function(mcemu_text, "static void sio2McLock("),
            extract_function(mcemu_text, "void hookSio2man("),
            extract_function(mcemu_text, "void Sio2McEmu("),
        ]
    )

    pademu_funcs = "\n\n".join(
        [
            extract_function(pademu_text, "void InstallSio2manHook("),
            extract_function(pademu_text, "static void hookSio2man25_1("),
            extract_function(pademu_text, "static void hookSio2man25_2("),
            extract_function(pademu_text, "static void hookSio2man51_1("),
            extract_function(pademu_text, "static void hookSio2man51_2("),
        ]
    )

    source = (
        HARNESS_C.replace("__MCEMU_SYS_FUNCS__", mcemu_sys_funcs)
        .replace("__MCEMU_FUNCS__", mcemu_funcs)
        .replace("__PADEMU_FUNCS__", pademu_funcs)
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "test_sio2man_hooks.c"
        bin_path = tmp / ("test_sio2man_hooks.exe" if sys.platform == "win32" else "test_sio2man_hooks")
        c_path.write_text(source, encoding="utf-8")

        cc_cmd = ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]
        if sys.platform != "win32":
            cc_cmd.append("-fsanitize=address,undefined")
        cc_cmd.extend([str(c_path), "-o", str(bin_path)])

        subprocess.run(cc_cmd, check=True)
        subprocess.run([str(bin_path)], check=True)


def main() -> int:
    check_static_wiring()
    run_host_harness()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
