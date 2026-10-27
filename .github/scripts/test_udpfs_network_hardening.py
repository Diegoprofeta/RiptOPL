"""UDPFS/UDP network-chain hardening (follow-ups to the original's PR #921).

* DEV9: sysInitDev9() reports whether DEV9 loaded, and the three UDP NIC chains (UDPFS Files, and the
  UDPBD/UDPFS-IMG block chain on its on-demand and boot paths) never load SMAP without it.
* IP conflict: the ministack export, the udpfs_ioman devctl and the loader all use one query value,
  the scan only queues the notice, and the menu frame hook shows it on the GUI thread.

Ported from the original's test of the same name; RiptOPL already carried these fixes. The
original's Makefile sub-make and RA workflow checks do not apply: RiptOPL builds every IRX from
ps2.yaml and has no RA release workflow yet.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def body(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]


failures = []


def check(what, ok):
    if not ok:
        failures.append(what)


# --- DEV9 ---
system = read("src/platform/system.cpp")
check("sysInitDev9 returns whether DEV9 loaded", "int sysInitDev9(void)" in system and
      "return dev9Loaded;" in body(system, "int sysInitDev9(void)"))
check("system.h declares the int result", "int sysInitDev9(void);" in read("include/system.h"))

udpfs = read("src/sources/udpfssupport.cpp")
loader = body(udpfs, "static void udpfsLoadModules(void)")
check("UDPFS Files refuses without DEV9 before loading SMAP",
      loader.index("if (!sysInitDev9())") < loader.index("udpfs_smap_irx"))
check("UDPFS Files releases the DEV9 reference it took", "sysShutdownDev9();\n        return;" in loader)
check("UDPFS Files keeps DEV9 and refuses a retry once SMAP is resident",
      loader.index("if (udpfsNicClaimed)") < loader.index("sysInitDev9()") and
      "udpfsNicClaimed = 1;" in loader and "if (!udpfsNicClaimed)\n        sysShutdownDev9();" in loader)


bdm = read("src/sources/bdmsupport.cpp")
check("a partial block chain also keeps the NIC claimed",
      "if (udpbdNicClaimed && !udpbdModLoaded) {" in bdm and "} else if (!udpbdNicClaimed) {" in bdm)
for signature in ("int bdmEnsureNetworkSourceModules(int protocol, u32 timeoutMs)",
                  "if (gEnableUDPBD && !udpbdNicClaimed && !ethGetModulesLoaded() && !udpfsGetModulesLoaded()) {"):
    start = bdm.index(signature)
    chain = bdm[start:bdm.index("smap_udpbd_irx", start)]
    check(f"block chain checks DEV9 first ({signature[:40]})",
          "int dev9Ready = sysInitDev9();" in chain and
          chain.index("if (!dev9Ready)") < chain.index("udpfs_smap_irx"))

# --- IP conflict notice ---
value = "0x55460001"
ioman = read("modules/network/udpfs_ioman/src/udpfs_ioman.c")
check("udpfs_ioman answers the conflict devctl", f"#define UDPFS_DEVCTL_IP_CONFLICT {value}" in ioman and
      "arp_ip_conflict(" in body(ioman, "static int udpfs_devctl("))
check("loader uses the same devctl value", f"#define UDPFS_DEVCTL_IP_CONFLICT {value}" in udpfs)
check("ministack exports arp_ip_conflict in slot 7",
      "DECLARE_EXPORT(arp_ip_conflict)" in read("modules/network/udpfs_ministack/src/exports.tab") and
      "DECLARE_IMPORT(7, arp_ip_conflict)" in read("modules/network/udpfs_ministack/include/mstack.h"))
check("udpfs_ioman imports it", "I_arp_ip_conflict" in read("modules/network/udpfs_ioman/src/imports.lst"))
check("udpfs_bd does not need it", "I_arp_ip_conflict" not in read("modules/network/udpfs_bd/src/imports.lst"))
conflict = body(udpfs, "static void udpfsCheckIpConflict(void)")
check("the scan only queues the notice", "warning(" not in conflict and "udpfsIpConflictNotice = 1;" in conflict)
check("the notice is shown once", "udpfsIpConflictWarned = 1;" in conflict)
check("the GUI frame hook shows it", "udpfsShowPendingNotice();" in body(read("src/app/opl.cpp"), "void menuUpdateHook()"))

if failures:
    raise SystemExit("FAIL:\n  " + "\n  ".join(failures))
print("PASS: DEV9-gated UDP chains and IP-conflict notice")
