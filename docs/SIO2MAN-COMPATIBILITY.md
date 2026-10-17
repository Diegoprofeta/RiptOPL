# SIO2MAN v1/v2 Compatibility for VMC, PADEMU, and MX4SIO

## Problem Summary

PlayStation 2 games and IOP modules can register either or both `sio2man` export tables:

- `sio2man` v1 (`0x100` family), where the second transfer entry is export `#49`.
- `sio2man` v2 (`0x200` family), where the second transfer entry is export `#51` and `sio2_mtap_change_slot_set` shifts later entries.
- PS2SDK `sio2man`, which registers both v1 (`0x101`) and v2 (`0x201`) tables so older and newer IOP modules can bind against the same driver.

Before this fix:

1. `mcemu` and `pademu` stored only one set of original `sio2man` function pointers (`pSio2man25`, `pSio2man51`, `psio2_mc_transfer_init`, `psio2_transfer_reset`). When a `sio2man` implementation registered both v1 and v2 export tables, hooking the second table overwrote the saved callbacks for the first table.
2. `StartNow()` and `install_sio2hook()` only looked up `sio2man` version `0x201`. If a v1 table was already resident before hooks were installed, it was missed.
3. `HookExportEntry()` replaced only one slot in an export table. In `sio2man` tables where multiple export indices alias the same underlying routine (such as `sio2_mc_transfer_init` and `sio2_pad_transfer_init`, or `sio2_transfer` and `sio2_transfer2` in ROM `sio2man`), callers importing the alias could bypass the hook or overwrite saved original pointers on repeated installation.
4. `Sio2McEmu()` always unlocked and relocked `SIO2` through a single `psio2_transfer_reset` / `psio2_mc_transfer_init` pair instead of matching the `sio2man` version active for that transfer.
5. `ee_core` only preloaded PS2SDK `sio2man` when `MX4SIO` was active, not when `VMC` or `PADEMU` was active without `MX4SIO`.

## Solution Overview

### 1. Preload PS2SDK `sio2man` for VMC, PADEMU, and MX4SIO

- `src/platform/system.cpp` now packs `sio2man_irx` (`OPL_MODULE_ID_SIO2MAN`) whenever `CORE_IRX_MX4SIO`, `CORE_IRX_VMC`, or `PADEMU` is active.
- `ee_core/src/iopmgr.c` loads `OPL_MODULE_ID_SIO2MAN` in `ResetIopSpecial()` before the game-mode switch and before `VMC` (`mcemu`), `PADEMU`, or `MX4SIO` (`mx4sio_bd`) modules start.
- `OPL_MODULE_ID_MX4SIOBD` is only started if `OPL_MODULE_ID_SIO2MAN` loaded cleanly (`sio2manLoaded > 0`).

### 2. Separate v1 and v2 Callback Storage and Wrappers

- `modules/mcemu` and `modules/pademu` now maintain two-element arrays (`[0]` for v1, `[1]` for v2) for:
  - `pSio2man25[2]`
  - `pSio2man51[2]`
  - `psio2_mc_transfer_init[2]` (`mcemu`)
  - `psio2_transfer_reset[2]` (`mcemu`)
- Dedicated wrapper callbacks (`hookSio2McInit_1`/`_2`, `hookSio2man25_1`/`_2`, `hookSio2man51_1`/`_2`, `Sio2McEmu_1`/`_2`) preserve the calling table version across the entire transfer lifecycle, including `pademu_hookSio2man` chaining and `mc2_s1` direct DMA requests (`temp_packet_version`).

### 3. Alias-Safe and Idempotent Export Table Hooking

- `HookExportEntry()` in `modules/mcemu/mcemu_sys.c` and `modules/pademu/sys_utils.c` scans the full export table and replaces every slot that points to the same target function, returning the original target pointer.
- `InstallSio2manHook()` checks `if (old != hookFn)` before updating saved function pointers, preventing self-referential recursion if a table is hooked more than once or shares aliased entries.

### 4. Version-Matched Unlock/Lock Around VMC I/O

- `Sio2McEmu(Sio2Packet *sd, int ver)` calls `sio2McUnlock(ver)` before backing-store I/O and `sio2McLock(ver)` afterward, falling back to the opposite version slot (`ver ^ 1`) only if the primary slot is `NULL`.
