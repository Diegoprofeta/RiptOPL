# First hardware report: launch-regression triage (2026-10-18)

Source: FifthFox's Discord report supplied by Nathan. Build is **likely latest
rolling Korium**, as Nathan clarified; exact tested ELF/hash and known-good
original build are unknown. At triage time rolling-korium points to `1c4822fc`;
this identifies the current channel, not the tester's binary.

| Area | Evidence/status | Next boundary |
| --- | --- | --- |
| UI boot/art | Tester reports faster startup/art loading; qualitative only. | No performance benchmark claimed. |
| Native OPL PS2 over iLink | Tester reports failed launch and absent PS2 logo. Still reported; no reproduced cause/fix. | Locate failure before logo validation, in game-side module init, image IO or handoff; compare same game/device/config. |
| Neutrino across devices | Tester reports needing more compatibility modes. Still reported; specific titles/modes unknown. | Compare resolved config/defaults and final argv with the original; avoid arbitrary delays. |
| Ember | Provisionally reported working on tested devices. | Exact device/title coverage unspecified. |
| POPStarter non-USB | Tester suspects USB-only success and explicitly needs more confirmation. | Per-device driver pair, MC installation, selector and reset ownership audit. |

## Confirmed code/asset defect, separately scoped

`vcdBdmaPairSig` expects iLink usbhdfsd size 23452, but our tracked and shipped
`ship/POPS/usbhdfsd.irx.ilink` is 21609 bytes. USBD is 48500 bytes. Every other
shipped pair matches its table entry. Thus marked validation and unmarked manual
pair recognition can reject our own iLink release files. Correct the expected
canonical length to 21609 while preserving the previously accepted 23452-byte
iLink pair with its matching 48500-byte USBD module. Exercise both actual validators against sizes obtained from
all six shipped pairs. Old code fails; corrected code passes under ASan/UBSan.
Wrong family/marker, missing or truncated pairs remain rejected. The previous
iLink size is accepted only for iLink with the matching USBD size. This retains
the existing size-based recognition policy; it does not authenticate IRXs.

**Code-addressed, awaiting hardware confirmation.** Preparation is best-effort
and may continue with the current MC pair, so this defect does not establish why
POPStarter failed on hardware. It cannot explain native PS2/iLink failure by
itself. No runtime success, timing fix or SDK deficiency is claimed.

## Source audit so far

- Native BDM iLink dispatch, iLinkman/IEEE1394 module embedding and logo validation
  are present. This is not proof of successful module loading or device IO.
- Installed ps2build packages iLinkman and IEEE1394_bd_mini are present. Package
  existence/build success do not prove runtime imports or bus initialization.
- `convertCompatmaskToModes` is identical to original `b35ff38c`; mode conversion
  alone is not a demonstrated migration delta. The device-name helper differs
  only in the as-yet-unmerged DVR mapping, unrelated to this report.
- Original source has the same 23452 expectation. Its actual published iLink
  driver bytes have not been independently checked; do not claim the original
  release has this same asset mismatch without verifying that artifact.
- Pending #62's syscall GP/context fix may be relevant to game-core behavior,
  but has no tester evidence tying it to these failures.

## Small reproducible comparison requested when details become available

For each failing path, record one game ID, device/adapter and filesystem, console
model, core/companion version, all effective modes/free-text args, PS2-logo setting,
VMC/cheat/pademu settings, last visible stage, and the matching known-good original
build. Change one variable per comparison. Exact tester details are useful for
reproduction but do not block source auditing. Do not deploy/reset a console merely
to investigate this report without an authorized hardware test.

## Follow-up: build 4009 and native-logo audit

FifthFox's later report names C++ 4009 (exact ELF hash/channel unverified).
After removing MC0's POPStarter directory and configuring assault drivers,
POPStarter reportedly works on iLink and other tested devices except APA SSD,
which reaches POPStarter and crashes. This supersedes the tentative USB-only
finding; do not attribute it to PR #64, because build/MC environment changed.
Ember works on tested devices, explicitly excluding APA SSD. USB/APA OPL and
Neutrino work without extra modes; MX4SIO OPL works; MMCE Neutrino needs modes.
Other core/device combinations are not established. Logo remains absent despite
selection and a visible Neutrino -logo argument. Details are preserved in issue #63.

The native CheckPS2Logo routine differed from original b35ff38c only in C++
pointer arithmetic and UI calls. It validates decrypted checksum and console
region before enabling PS2LOGO, which must also exist in ROM. Neutrino separately
handles its own logo; -qb is deliberately generated on USB/iLink to preserve the
inherited IOP. Neither logo absence nor a visible token proves launch execution.

A confirmed inherited native edge case: fd > 0 refused a valid file descriptor
zero, even though BDM launch accepts fd >= 0. Change only the file-backed logo
branch to fd >= 0; HDD remains selected by fd == 0 and lba > 0. A synthetic-logo
fixture compiles the actual validator and fails on the old fd-zero condition,
then passes normal/fd-zero reads, invalid descriptor, 48-sector HDD bound, region
accept/reject and short-read rejection after correction. Synthetic bytes contain
no game/ROM data. This does not establish that tester build 4009 received fd zero,
and it cannot explain Neutrino's separate logo behavior. No console fix or SDK
deficiency is claimed.

## Native BDM alignment audit and matched test procedure (2026-10-19)

Original commit `35af507b6a78a10c6b567c70e067742cf59097cf` ports upstream OPL
#1783: ZSO reads can provide an unaligned destination to a block driver that
requires word-aligned buffers. This migration still passed those buffers through.
An actual-function host fixture fails at offsets 1-3 against the old source and
passes with the original's 64-byte-aligned 2 KiB bounce buffer. Aligned requests
remain direct; incomplete bounce reads never copy their failed sector into the
destination. Synthetic driver data does not establish DMA behavior, console
success, or that the reported iLink title used ZSO or an unaligned buffer.

For an authorized console test, retain the ELF SHA-256 and source commit from
the edition's `BUILD-MANIFEST.json`, companion version, console model, adapter,
filesystem, game ID and effective per-game configuration. Compare the same
title/device/configuration on the known-good original, the pre-fix migration and
the candidate. For native OPL, use equivalent ISO/ZSO images where available;
record the last visible stage, logo result, boot and IGR separately. Do not infer
Neutrino behavior from the native BDM change. Keep MMCE Neutrino title/modes/argv
and APA POPStarter partition/selector/MC-driver comparisons as separate rows.

Before publishing a console claim, record the actual tested hash rather than
identifying it only by a moving rolling tag. No console run or SDK deficiency
is established by this host regression.
