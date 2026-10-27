# DESR DVR: discovery and launch contract

Off by default. With Game Sources > **DESR DVR ISOs (experimental)** on, the HDD page checks the
DVRP capability bit (`SPD_CAPS_DVR`). Only a PSX DESR has it, so ordinary PS2 models never load a
module or touch a partition. On a DESR the page loads `dvrdrv` and `dvrfile` once, mounts
`dvr_hdd0:__xcontents` and `__xdata` read-only as `dvr_pfs0:`/`dvr_pfs1:`, and lists the `.iso`
files in their root, `/DVD` and `/CD` folders after the HDL rows. A failed or truncated scan keeps
the last-good rows. Nothing is ever written, created or formatted on a DVR partition.
**NOT TESTED on DESR hardware.**

Before a DVR row tears down the GUI, it must call
`sysNeutrinoPreflight` and `sysNeutrinoArgsPreflight` with the same launch values.
The preflight requires `config/bsd-dvr.toml` or adjacent `bsd-dvr.toml`, followed
by `modules/dvrdrv.irx`, `modules/dvrfile.irx` and `modules/dvrfile_fhi.irx`, beside
the selected Neutrino ELF. Every successful read-only probe is closed. Missing
files, missing directory separators and overlong paths refuse the launch while
the menu is still available.

DVR must use the companion's PSX-mode transition. Active `-qb` is refused.
Active `-bsd=` and `-bsdfs=` overrides are also refused for DVR: the launch owns
its filesystem backend, and forwarded user tokens must not silently replace it
with a block-device configuration. Disabled `$-` tokens and options after `--b`
retain the existing parser semantics; global and per-game option scopes remain
independent. Other transports retain their existing behavior.

The argv builder emits `-bsd=dvr` and the supplied `dvr_pfsN:` path, ignores the
filesystem picker for this backend, and adds neither quickboot nor PS2 logo.
Argument count/byte-budget refusal still applies before teardown.

The normal bundled Neutrino is not a DVR companion. File presence is only a
preflight check; it does not authenticate a companion build or establish module
ABI compatibility. A matching DVR-capable companion and its PSX reset behavior
must be validated during the later platform port and on DESR hardware.

The installed ps2build SDK has `dvr` and `dvrfile` driver packages. That does not
establish that their binaries can replace a companion's game-side IRXs. The
custom PCCF driver sources are a separate application port. No SDK deficiency
has been confirmed by this launch-contract work.
