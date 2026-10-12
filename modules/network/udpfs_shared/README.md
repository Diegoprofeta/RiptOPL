# Shared UDPFS transport implementation

`udpfs_core.c` and `udprdma.c` are the canonical transport sources for both UDPFS
IOP drivers. The filesystem (`udpfs_ioman`) and block-device (`udpfs_bd`) driver
builds each compile these same sources through local single-include wrappers,
with their **existing**, distinct `FEATURE_UDPFS_IOMAN` and `FEATURE_UDPFS_BD` flags.

The per-variant `src/*.h`, `main.c`, module import lists, entry points,
registration names, and Makefiles remain separate. Do not co-load the variants:
both still depend on the mutually exclusive network stack selection.

Original source: rickgaiser/neutrino UDPFS transport, pinned source provenance
and local changes recorded in the respective `ORIGIN.txt` files.

Ported from NathanNeurotic/Open-PS2-Loader at
`6d04b40e8d857368110265a18ec9fc90b7c316c4` (public PRs #908, #913 and #921).
The transport resets session sequence state after discovery and waits through
stale ACKs without spending a retry. The ministack announces the PS2's address
before discovery. Filesystem operation serialization from public PR #904 is
retained in the variant wrapper, outside this shared transport.

The SDK port uses `u32` for `WaitEventFlag` outputs, as required by its IOP API.
Packet formats, retry limits, module identities and per-variant compile flags
are preserved. ps2build compiles the local wrappers listed in `ps2.yaml`;
`tools/build.py` enables LLVM header dependencies so edits here invalidate both.

Run `python3 .github/scripts/test_udpfs_shared_transport.py`,
`python3 .github/scripts/test_udpfs_transport.py` and
`python3 .github/scripts/test_udpfs_serialization.py`, then build with both GCC
and LLVM. These host tests do not establish real-console acceptance.
