"""Test regression repairs for Issue #830 (Neutrino exFAT VMC budget & creation) and Issue #831 (Beat Down title compat defaults)."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
src_support = (root / 'src/sources/supportbase.cpp').read_text(encoding='utf-8')
src_bdm = (root / 'src/sources/bdmlaunch.cpp').read_text(encoding='utf-8')
src_gui = (root / 'src/ui/guigame.cpp').read_text(encoding='utf-8')

# 1. sbTitleCompatDefaults must not carry the serials #968 added for Beat Down (original #1009). None of them
# is Beat Down (SLUS_212.42 is Burnout Revenge USA), so they forced Synchronous Reads on other games and never
# reached Beat Down itself (SLUS_211.50 / SLES_535.05 / SLPM_661.81 / SLPM_668.19 / SLPM_664.46). No real Beat
# Down serial gets a default either until a console test shows a mode that fixes the #831 hang.
table = src_support[src_support.index('sbTitleCompatDefaults[] = {'):]
table = table[:table.index('};')]
for startup in ('SLUS_212.42', 'SLES_535.58', 'SLPM_660.94', 'SLKA_253.13',
                'SLUS_211.50', 'SLES_535.05', 'SLPM_661.81', 'SLPM_668.19', 'SLPM_664.46'):
    assert f'"{startup}"' not in table, f"{startup} must not have a title compat default"

print("PASS: sbTitleCompatDefaults has no unverified Beat Down (#831) entries")

# 2. Verify guiGameResolveEffectiveCore exists in src/ui/guigame.cpp and is called in VMC dialogs
assert 'guiGameResolveEffectiveCore' in src_gui, "guiGameResolveEffectiveCore must exist in src/ui/guigame.cpp"
assert 'coreLoader = guiGameResolveEffectiveCore(configSet, support, id);' in src_gui, "guiGameResolveEffectiveCore must update coreLoader in VMC paths"

print("PASS: guiGameResolveEffectiveCore resolves effective core in VMC dialogs")

# 3. Execute the production NeutrinoLauncher::fragBudgetOk from src/sources/bdmlaunch.cpp
start = src_bdm.index('int NeutrinoLauncher::fragBudgetOk(')
production_fn = src_bdm[start:src_bdm.index('\n}\n', start) + 3]
budget_message = json.loads(re.search(r'^- label: NEUTRINO_VMC_FRAG_BUDGET_CONTINUE\n  string: (".*")$',
                                      (root / 'lng/tmpl/_base.yml').read_text(encoding='utf-8'), re.M).group(1))

harness = r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NEUTRINO_VMC_SLOTS 2
#define O_RDONLY 0
#define USBMASS_IOCTL_GET_FRAGLIST 2
#define LOG(...) ((void)0)
typedef struct { char arg[NEUTRINO_VMC_SLOTS][160]; } neutrino_vmc_args_t;
class NeutrinoLauncher {
public:
    static constexpr int kMaxFrags = 64;
    int fragBudgetOk(const char *isoPath, neutrino_vmc_args_t *vmcArgs, int isUdp);
};
enum { _STR_ERR_VMC_FRAGMENTED_CONTINUE = 1, _STR_NEUTRINO_TOO_FRAGMENTED, _STR_NEUTRINO_TOO_FRAGMENTED_NET,
       _STR_NEUTRINO_VMC_FRAG_BUDGET_CONTINUE };
static int msgBoxResponse = 1, msgBoxCalled = 0;
static char lastMsgBox[256];
static const char *_l(int id) {
    assert(id != _STR_ERR_VMC_FRAGMENTED_CONTINUE);
    return id == _STR_NEUTRINO_VMC_FRAG_BUDGET_CONTINUE ? @BUDGET_MESSAGE@ : "Neutrino: %d/%d fragments";
}
namespace host {
struct Ui {
    int msgBox(const char *text, int, void *) { msgBoxCalled++; snprintf(lastMsgBox, sizeof(lastMsgBox), "%s", text); return msgBoxResponse; }
    void warning(const char *, int) {}
};
static Ui instance;
static Ui &ui() { return instance; }
}
static void *gAutoLaunchBDMGame = NULL;
static int stubIsoFrags, stubVmc0Frags, stubVmc1Frags;
static int open(const char *path, int) { return !strcmp(path, "iso") ? 10 : strstr(path, "slot0") ? 20 : strstr(path, "slot1") ? 21 : 30; }
static int close(int) { return 0; }
static int ps2sdk_get_iop_fd(int fd) { return fd; }
static int fileXioIoctl2(int fd, int, void *, int, void *, int) { return fd == 10 ? stubIsoFrags : fd == 20 ? stubVmc0Frags : fd == 21 ? stubVmc1Frags : 0; }
@PRODUCTION_FUNCTION@
static NeutrinoLauncher launcher;
static int budget(neutrino_vmc_args_t *vmc, int iso, int v0, int v1, int udp = 0)
{
    stubIsoFrags = iso; stubVmc0Frags = v0; stubVmc1Frags = v1;
    return launcher.fragBudgetOk("iso", vmc, udp);
}
int main(void) {
    neutrino_vmc_args_t vmc;
#define ONE() (strcpy(vmc.arg[0], "-mc0=mass0:/VMC/slot0.bin"), vmc.arg[1][0] = '\0', msgBoxCalled = 0)
#define TWO() (strcpy(vmc.arg[0], "-mc0=mass0:/VMC/slot0.bin"), strcpy(vmc.arg[1], "-mc1=mass0:/VMC/slot1.bin"), msgBoxCalled = 0)
    ONE(); assert(budget(&vmc, 10, 5, 0) == 1 && vmc.arg[0][0] && !msgBoxCalled);
    ONE(); msgBoxResponse = 1; assert(budget(&vmc, 58, 8, 0) == 1 && msgBoxCalled == 1 && !vmc.arg[0][0] && strstr(lastMsgBox, "slot0"));
    ONE(); msgBoxResponse = 0; assert(budget(&vmc, 58, 8, 0) == -1 && msgBoxCalled == 1);
    msgBoxResponse = 1;
    ONE(); assert(budget(&vmc, 65, 2, 0) == 0 && !msgBoxCalled);
    TWO(); assert(budget(&vmc, 40, 2, 30) == 1 && msgBoxCalled == 1 && strstr(lastMsgBox, "slot1") && vmc.arg[0][0] && !vmc.arg[1][0]);
    TWO(); assert(budget(&vmc, 60, 5, 5) == 1 && msgBoxCalled == 2 && !vmc.arg[0][0] && !vmc.arg[1][0]);
    // A contiguous VMC can overflow a full ISO budget: explain the shared limit, not "fragmented" (original #983).
    ONE(); assert(budget(&vmc, 64, 1, 0) == 1 && msgBoxCalled == 1 && !vmc.arg[0][0]);
    assert(strstr(lastMsgBox, "65/64") && strstr(lastMsgBox, "Neutrino") && strstr(lastMsgBox, "physical Memory Card in slot 1"));
    assert(strstr(lastMsgBox, "slot0") && !strstr(lastMsgBox, "is fragmented"));
    ONE(); assert(budget(&vmc, 61, 3, 0) == 1 && !msgBoxCalled && vmc.arg[0][0]);
    // Mapping failures are not zero-fragment successes (original #991): no drop, no prompt.
    TWO(); assert(budget(&vmc, -5, 1, 1) == 0 && budget(&vmc, -5, 1, 1, 1) == 0);
    assert(budget(&vmc, 1, -5, 1) == 0 && budget(&vmc, 1, -5, 1, 1) == 0);
    assert(budget(&vmc, 1, 1, -5) == 0 && budget(&vmc, 1, 1, -5, 1) == 0);
    assert(!msgBoxCalled && vmc.arg[0][0] && vmc.arg[1][0]);
    return 0;
}
""".replace('@PRODUCTION_FUNCTION@', production_fn).replace('@BUDGET_MESSAGE@', json.dumps(budget_message))

with tempfile.TemporaryDirectory() as temp_dir:
    temp_path = Path(temp_dir)
    cfile = temp_path / 'test_harness.cpp'
    exe = temp_path / ('test_harness.exe' if os.name == 'nt' else 'test_harness')
    cfile.write_text(harness, encoding='utf-8')
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(cfile), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)

print("PASS: bdmNeutrinoFragBudgetOk handles VMC budget overflow gracefully without catch-22")
