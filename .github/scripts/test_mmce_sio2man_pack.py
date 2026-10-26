"""Compile the actual SIO2MAN packing condition, with and without PADEMU.

Original 11a5150e reports an MMCE hang when SDK SIO2MAN is preloaded. This
checks the migration's packing policy, not console or driver acceptance.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
system = (root / 'src/platform/system.cpp').read_text(encoding='utf-8').replace('\r\n', '\n')
failures = []

body_at = system.find('static unsigned int sendIrxKernelRAM(')
pack_at = system.find('SET_OPL_MOD_ID(OPL_MODULE_ID_SIO2MAN)', body_at)
cond_at = system.rfind('\n    if (', body_at, pack_at)
if body_at < 0 or pack_at < 0 or cond_at < 0:
    print('src/platform/system.cpp: SIO2MAN packing in sendIrxKernelRAM not found')
    sys.exit(1)
line = system[cond_at:system.index('\n', cond_at + 1)].strip()
match = re.fullmatch(r'if \((.*)\) \{', line)
if match is None:
    print('src/platform/system.cpp: unexpected SIO2MAN packing condition: %s' % line)
    sys.exit(1)
condition = match.group(1)
# Original #1021: the launch must not select MCEMU (and with it SIO2MAN) for a zero-size VMC image.
launch_at = system.index('void sysLaunchLoaderElf(')
launch_flag = re.search(r'    if \(([^\n]+)\)\n        modules \|= CORE_IRX_VMC;', system[launch_at:])
if launch_flag is None:
    print('src/platform/system.cpp: launch VMC selection not found')
    sys.exit(1)

defines = ''.join('#define %s %s\n' % m for m in re.findall(r'(?:#define\s+|constexpr int\s+)(CORE_IRX_\w+)\s*(?:=\s*)?(0x[0-9A-Fa-f]+)', system))
for name in ('CORE_IRX_MMCE', 'CORE_IRX_VMC', 'CORE_IRX_MX4SIO', 'CORE_IRX_USB', 'CORE_IRX_HDD'):
    if name not in defines:
        failures.append('src/platform/system.cpp: %s is not defined' % name)

PROGRAM = r'''
#include <stdio.h>
@DEFINES@
static int gEnablePadEmu;
#ifdef PADEMU
#define PADEMU_ARG || gEnablePadEmu
#else
#define PADEMU_ARG
#endif
static int packs(unsigned int modules, int padEmu)
{
    gEnablePadEmu = padEmu;
    return (@COND@) ? 1 : 0;
}
static unsigned int launch_modules(int discMode, int size_mcemu_irx)
{
    unsigned int modules = CORE_IRX_HDD;
    if (@LAUNCH@)
        modules |= CORE_IRX_VMC;
    return modules;
}
static int fails;
#define CHECK(c, m) do { if (!(c)) { printf("FAIL %s\n", m); fails++; } } while (0)
int main(void)
{
    CHECK(!packs(CORE_IRX_MMCE | CORE_IRX_VMC, 0), "MMCE game (VMC flag always set) gets no SDK SIO2MAN");
    CHECK(!packs(CORE_IRX_MMCE | CORE_IRX_VMC, 1), "MMCE game with PADEMU gets no SDK SIO2MAN");
    CHECK(packs(CORE_IRX_USB | CORE_IRX_VMC, 0), "USB game keeps the SDK SIO2MAN (#962)");
    CHECK(packs(CORE_IRX_HDD | CORE_IRX_VMC, 0), "HDD game keeps the SDK SIO2MAN (#962)");
    CHECK(packs(CORE_IRX_MX4SIO | CORE_IRX_VMC, 0), "MX4SIO game keeps the SIO2MAN it requires");
    CHECK(packs(CORE_IRX_MX4SIO, 0), "MX4SIO without VMC still gets SIO2MAN");
    CHECK(!packs(0, 0), "a disc launch without VMC, MX4SIO or PADEMU gets none");
#ifdef PADEMU
    CHECK(packs(CORE_IRX_HDD, 1), "PADEMU alone still packs SIO2MAN off MMCE");
#endif
    CHECK(!packs(CORE_IRX_MMCE, 0), "MMCE without VMC gets none");
    CHECK(!packs(CORE_IRX_MMCE, 1), "MMCE with only PADEMU gets none");
    CHECK(packs(CORE_IRX_ILINK | CORE_IRX_VMC, 0), "iLink VMC keeps SIO2MAN");
    CHECK(packs(CORE_IRX_ETH | CORE_IRX_VMC, 0), "network VMC keeps SIO2MAN");
    CHECK(!(launch_modules(0, 0) & CORE_IRX_VMC), "both VMC slots off select no MCEMU");
    CHECK(!packs(launch_modules(0, 0), 0), "an idle HDD launch leaves SIO2MAN to the game (#1021)");
    CHECK(launch_modules(0, 4096) & CORE_IRX_VMC, "an active VMC selects MCEMU");
    CHECK(!(launch_modules(1, 4096) & CORE_IRX_VMC), "disc mode never selects MCEMU");
    return fails ? 1 : 0;
}
'''

if not failures:
    for flavour, extra in (('standard', ''), ('pademu', '#define PADEMU\n')):
        program = extra + PROGRAM.replace('@DEFINES@', defines).replace('@COND@', condition).replace('@LAUNCH@', launch_flag.group(1))
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'pack.c'
            exe = Path(tmp) / ('pack.exe' if sys.platform == 'win32' else 'pack')
            src.write_text(program, encoding='utf-8')
            try:
                build = subprocess.run(['g++', '-std=c++17', '-Wall', '-Werror', '-o', str(exe), str(src)],
                                       capture_output=True, text=True, check=False, timeout=120)
            except subprocess.TimeoutExpired:
                failures.append('%s harness: gcc did not finish within 120 s' % flavour)
                continue
            if build.returncode != 0:
                failures.append('%s harness did not compile:\n%s' % (flavour, build.stderr))
                continue
            try:
                run = subprocess.run([str(exe)], capture_output=True, text=True, check=False, timeout=10)
            except subprocess.TimeoutExpired:
                failures.append('%s harness: did not finish within 10 s' % flavour)
                continue
            if run.returncode != 0:
                failures.extend('%s: %s' % (flavour, l) for l in (run.stdout.strip().splitlines() or ['exited %d' % run.returncode]))

iopmgr = (root / 'ee_core/src/iopmgr.c').read_text(encoding='utf-8').replace('\r\n', '\n')
mmce_case = iopmgr[iopmgr.find('case MMCE_MODE:'):]
mmce_case = mmce_case[:mmce_case.find('break;')]
if 'OPL_MODULE_ID_SIO2MAN' in mmce_case:
    failures.append('ee_core/src/iopmgr.c: the MMCE case must not load SIO2MAN')

if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('MMCE launches get no SDK SIO2MAN; USB, HDD and MX4SIO keep it; idle VMC selects none')
