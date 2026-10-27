"""Every interactive dialog row carries a hint, except the dialog buttons and IP octets the original also leaves bare.

The original's src/dialogs.c leaves exactly these rows without one; a new row with -1 fails here.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
dialogs = (root / "src/ui/dialogs.cpp").read_text(encoding="utf-8")
bare = sorted(re.findall(r"\{UI_(?:BUTTON|ENUM|BOOL|STRING|INT|PASSWORD|COLOUR), ([A-Z][A-Z0-9_]+), \d+, \d+, -1,", dialogs))
allowed = sorted(["NETCFG_OK", "NETCFG_RECONNECT", "NETCFG_POPS_UDPFS", "POPS_OVERWRITE_KEEP", "POPS_OVERWRITE_REPLACE",
                  "VCDUSB_BTN_EXFAT", "VCDUSB_BTN_FAT32", "VMC_PROGRESS"] + ["NETCFG_POPS_SMB_IP_%d" % i for i in range(4)])
assert bare == allowed, "rows without a hint: %s" % sorted(set(bare) - set(allowed))
print("PASS: every interactive dialog row has a hint except the original's bare dialog buttons")
