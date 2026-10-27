"""A device POPS/ folder holding an older release's BDMA pair: the launch equip must say so (original #1026).

When the shipped driver size changes, anyone who updates the ELF but not the drive's POPS/ folder used to
get the old pair copied to the card on every launch, the size check after it failing, and a "card write"
error that never happened. A launch now installs only the pair this release ships and reports -5
(BDMA_ERR_OLD) when the seek path holds only another one. The Settings page's manual equip is unchanged.

Executes the real vcdSourceFileSize / vcdBdmaPairIsShipped / vcdProbeBdmaPair against the shipped sizes,
with an MMCE-style source that has no SEEK_END, and pins the routing of the launch and manual callers.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'src/sources/vcdsupport.cpp').read_text(encoding='utf-8').replace('\r\n', '\n')
failures = []


def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


table = re.search(r'static const bdma_pair_sig_t vcdBdmaPairSig\[[^;]+;', source, re.S).group()
suffixes = ['usbexfat', 'mx4sio', 'mmce', 'ata', 'ilink', 'udpfs']
shipped = [[(root / 'ship/POPS' / f'{name}.{suffix}').stat().st_size for name in ['usbd.irx', 'usbhdfsd.irx']]
           for suffix in suffixes]

program = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define LOG(...) ((void)0)
constexpr int O_RDONLY = 0, VCD_BDMA_MODE_COUNT = 7, VCD_COPY_CHUNK = 16 * 1024;
struct bdma_pair_sig_t { int usbdSize, hdfsdSize; };
@TABLE@
static int size[2], present[2], noSeekEnd, pos[2];
static int which(const char *p) { return strstr(p, "usbhdfsd") != nullptr; }
static int open(const char *p, int flags) { assert(flags == O_RDONLY); int i = which(p); pos[i] = 0; return present[i] ? 10 + i : -1; }
static int close(int fd) { assert(fd == 10 || fd == 11); return 0; }
static int lseek(int fd, int, int whence) { assert(whence == SEEK_END); return noSeekEnd ? -1 : size[fd - 10]; }
static int read(int fd, void *, int n) { int i = fd - 10, r = size[i] - pos[i] < n ? size[i] - pos[i] : n; pos[i] += r; return r; }
static int vcdBdmaPairIsShipped(const char *src0, const char *src1, int mode);
@PROBE@
@SIZE@
@SHIPPED@
static const int ship[][2] = @SIZES@;
int main()
{
    for (noSeekEnd = 0; noSeekEnd < 2; ++noSeekEnd)
        for (int mode = 1; mode < VCD_BDMA_MODE_COUNT; ++mode) {
            char stale[96] = "";
            size[0] = ship[mode - 1][0]; size[1] = ship[mode - 1][1]; present[0] = present[1] = 1;
            assert(vcdProbeBdmaPair("d:/POPS/usbd.irx", "d:/POPS/usbhdfsd.irx", mode, 1, stale, sizeof(stale)) == 1 && !stale[0]);
            size[1] += 368; // another release's driver
            assert(vcdProbeBdmaPair("d:/POPS/usbd.irx", "d:/POPS/usbhdfsd.irx", mode, 1, stale, sizeof(stale)) == 0);
            assert(!strcmp(stale, "d:/POPS/usbhdfsd.irx"));
            assert(vcdProbeBdmaPair("e:/POPS/usbd.irx", "e:/POPS/usbhdfsd.irx", mode, 1, stale, sizeof(stale)) == 0);
            assert(!strcmp(stale, "d:/POPS/usbhdfsd.irx")); // the first stale file is the one reported
            assert(vcdProbeBdmaPair("d:/POPS/usbd.irx", "d:/POPS/usbhdfsd.irx", mode, 0, stale, sizeof(stale)) == 1); // manual: any pair
            present[1] = 0; stale[0] = 0;
            assert(vcdProbeBdmaPair("d:/POPS/usbd.irx", "d:/POPS/usbhdfsd.irx", mode, 1, stale, sizeof(stale)) == 0 && !stale[0]);
        }
    puts("BDMA stale pair: shipped pairs install, another release's pair is passed over and named, MMCE sizes read through");
    return 0;
}
'''
program = (program.replace('@TABLE@', table).replace('@PROBE@', function('static int vcdProbeBdmaPair('))
           .replace('@SIZE@', function('static int vcdSourceFileSize('))
           .replace('@SHIPPED@', function('static int vcdBdmaPairIsShipped(const char *src0, const char *src1, int mode)\n{'))
           .replace('@SIZES@', '{' + ','.join('{%d,%d}' % tuple(s) for s in shipped) + '}'))

with tempfile.TemporaryDirectory() as tmp:
    cpp, exe = Path(tmp) / 'stale.cpp', Path(tmp) / 'stale'
    cpp.write_text(program, encoding='utf-8')
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=20)

ensure = function('void vcdEnsureBdmaForLaunch(')
usb = function('void vcdApplyUsbModeForLaunch(')
if ensure.count('equipBdma(') != 2 or ensure.count(', NULL, 1)') != 2:
    failures.append('vcdEnsureBdmaForLaunch: every launch equip must install only the shipped pair')
if 'equipBdma(VCD_BDMA_SRC_USB, mode, diag, sizeof(diag), NULL, 1)' not in usb:
    failures.append('vcdApplyUsbModeForLaunch: the USB launch equip must install only the shipped pair')
if 'popsDir, 1);' not in function('int vcdEquipBdmaFromPops('):
    failures.append('vcdEquipBdmaFromPops: the HDD __common launch equip must install only the shipped pair')
if 'return gVcdSupport.equipBdma(source, mode, diag, diagSize);' not in function('int vcdEquipBdma('):
    failures.append('vcdEquipBdma: the Settings page equip must keep installing the pair the user chose')
for name, body in (('vcdEnsureBdmaForLaunch', ensure), ('vcdApplyUsbModeForLaunch', usb)):
    if not re.search(r'else if \(er == -5\)\n\s+host::ui\(\)\.warning\(_l\(_STR_BDMA_ERR_OLD\), 6\);', body):
        failures.append(name + ': -5 must show BDMA_ERR_OLD, not a card write error')
if 'if (er == -4 && older)' not in ensure:
    failures.append('vcdEnsureBdmaForLaunch: a UDPFS search that only met older pairs must report them')
labels = re.findall(r'^- label: (\S+)', (root / 'lng/tmpl/_base.yml').read_text(encoding='utf-8'), re.M)
at = labels.index('BDMA_ERR_OLD') if 'BDMA_ERR_OLD' in labels else -1
if at < 1 or labels[at - 1] != 'HINT_MODE8':
    failures.append('lng/tmpl/_base.yml: BDMA_ERR_OLD must be appended right after HINT_MODE8')

if failures:
    print('\n'.join('FAIL: ' + f for f in failures))
    sys.exit(1)
print('BDMA stale pair: launch equips install only the shipped pair; Settings equip unchanged')
