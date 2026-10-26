"""New HDD VMCs ask PFS for every zone up front, and launches only trust committed maps (original #1014).

PFS grows a file write by write from small free runs, so a new card on a used partition can need
more segments than native mcemu's PFS map holds. genvmc requests the whole card in one PIOCALLOC
before the first write (best effort). pfs0: is mounted write-back, so the launch and the creation
check commit PFS's cache before reading the inode off the disk; test_pfs_vmc_inode.py executes the
inode validation itself. This pins the routing between EE and IOP.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[2]
read = lambda p: (root / p).read_text(encoding='utf-8')
genvmc, header = read('modules/vmc/genvmc/genvmc.c'), read('modules/vmc/genvmc/genvmc.h')
sysvmc, hdd = read('src/platform/sysvmc.cpp'), read('src/sources/hddsupport.cpp')
failures = []

def body(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}\n', start)]

if 'int VMC_flags;' not in header or 'typedef struct\n{\n    char VMC_filename' in sysvmc:
    failures.append('the EE must send genvmc.h createVMCparam_t, including VMC_flags')
fmt = body(genvmc, 'static int vmc_mcformat(')
alloc = fmt.find('PIOCALLOC')
if alloc < 0 or not (fmt.index('O_CREAT | O_TRUNC') < alloc < fmt.index('mc_writecluster(')):
    failures.append('vmc_mcformat: the reservation must follow the create and precede the first write')
if 'genvmc_request.VMC_flags & VMC_CREATE_PFS_RESERVE' not in fmt:
    failures.append('vmc_mcformat: the reservation must be limited to VMC_CREATE_PFS_RESERVE jobs')
if 'I_ioctl2' not in read('modules/vmc/genvmc/imports.lst'):
    failures.append('genvmc imports.lst: ioctl2 is not imported')
if 'createParam.VMC_flags = createFlags;' not in body(sysvmc, 'int sysCheckVMCEx('):
    failures.append('sysCheckVMCEx: the creation flags are not sent')
if 'sysCheckVMCEx(gHDDPrefix, "/", name, createSize, NULL, VMC_CREATE_PFS_RESERVE)' not in body(hdd, 'int HddSource::checkVmc('):
    failures.append('HddSource::checkVmc: HDD creation does not request the PFS reservation')
launch = body(hdd, 'void HddSource::launch(')
if not re.search(r'int synced = hddSyncForVMCMap\(\);.*synced \? hddGetFileBlockInfo\(', launch, re.S):
    failures.append('HddSource::launch: the VMC map is read without committing the PFS cache first')
if 'hddClassifyVMCMap(nparts)) == NATIVE_VMC_OK' not in launch:
    failures.append('HddSource::launch: an inode-only map (no data segment) must not activate a card')

if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('HDD VMC: PFS reservation routed to genvmc, committed and non-empty maps required at launch')
