# C++/ps2build migration: production parity ledger

Current continuation tracker: [issue #20](https://github.com/NathanNeurotic/RiptOPL/issues/20).
PRs #18/#19 and the full site import #17 are merged; Pages and the independent
wiki import are published. GCC/LLVM, host gates and all three complete release
candidate kits pass. Publication and physical-console acceptance remain open.
PR #21 merged the useful changes from PRs #12–#16 as `6988499b`; the originals
are closed as superseded. See the checkpoint for exact final CI/artifact refs.
PR #22 merged production #922 (`0a1a593a`) into `d54dfc57`. Fresh integration
GCC/LLVM, host and all three kit jobs pass; downloaded kits pass the publisher's
independent verification against that exact integration SHA. The absent newer
RA browser/Caduceus methods remain part of the broader RA port.

Branch `codex/favorites-parity-903` adapts Favorites from production #903
(`a73fb2e4`) and #904 (`906cdafe`) to `FavSupport`, `Notifications` and the C++
theme engine. PR #23 is merged as `daae402e`, with fresh integration compiler,
host and three-kit CI plus independent downloaded artifact verification passing.
PR #24 merged as `7bcb77b3`; its 32-build GCC/LLVM configuration matrix and
three standard kits pass fresh CI and independent artifact verification.
PR #25 merged POPS #904/#909 and UL bounds/recovery as `4157d5a2`; all final
integration gates, 32 configuration artifacts and three kits pass verification.
PR #27 merged older feature gaps #885/#887/#889/#898; PR #29 merged automatic
VMC creation and newer Ember missing-core behavior; PR #30 handles truncated
port downloads. Final integration `39eda4b8` passes compiler/host/32-configuration
and three-kit checks, including independent downloaded package verification.
PR #31 merged Favorites read/write failure safeguards and sdk-core v2026.10.13
native sockets at `d74bb85b`; final compiler/host/32-configuration/three-kit CI
and independent downloaded artifact verification pass. Durable replacement is
still open. PR #32 merged optional CFG list titles at `cd787705`; final native, compiler,
host, 32-configuration and three-kit validation passes, including all 35
downloaded package checks. Pages #33 deployed and scoped Wiki guidance is
published. PR #34 merged the VMC follow-ups at `01affe4d`, with final compiler/host/32-configuration/three-kit checks and all 35 downloaded packages verified. The current branch ports Favorites staged recovery; see the checkpoint.

This ledger records verified ports into the C++/ps2build repository. It does not
claim that the entire public repository is synchronized. The public source
snapshot used for the ports below is Open-PS2-Loader commit
`6d04b40e8d857368110265a18ec9fc90b7c316c4` for the initial rows,
`0a1a593ade393d2c1d28bafb09ea8f3c5cb63706` for #922, and
`90566eb863f9ed3771cdbc9702a5611b55f8ddd9` for the POPS continuation. The older
feature bodies were compared at `a0ca55c54cb32b801423a4fdc800968ff4f62c2d`.

| Public change | Destination state before this port | Port and scope |
| --- | --- | --- |
| #885: quoted custom-core configuration values | Quoted values retained escaping on each read; repeated saves could grow/corrupt backslashes and quotes. | Decode only escaped backslash and quote before enforcing the stored-value bound; preserve unknown escapes and bare values. Actual config save/read sanitizer coverage includes repeated cycles and maximum escaped values; the old body fails the same test. Existing custom path consumers remain C++ methods. |
| #887: Ember image filtering | Any subdirectory could become a game row, including VMC/group/nested-only folders. | Require a top-level case-insensitive CUE, EXE or BIN image in each game directory; inspect the directory instead of trusting d_type. Actual scan tests cover both separator forms and misleading entry types. PR #29 subsequently adapts newer missing-core listing and diagnostics; see AUTOMATIC-VMC.md and the checkpoint. |
| #889: VMC failure recovery and Neutrino warnings (partial) | Failed/short cluster writes leaked the abort semaphore; the explicit VMC dialog checked contiguity even for Neutrino. | Release the semaphore on failed/short writes and failed seeks, stop before writing after seek failure, and skip contiguity probes/warnings for effective Neutrino selection. Actual C recovery tests fail against the old body; existing non-destructive VMC checks remain. PR #29 subsequently adapts the automatic-VMC launch hook through GameSource; see AUTOMATIC-VMC.md. |
| #898: checked explicit SMB refresh | Explicit ETH Refresh did not probe a live SMB session; unconditional reconnect would disturb ART/BGM handles. | Run ECHO through EthSupport and serialized IO; healthy sessions retain handles while requesting a deferred list refresh, failed/missing sessions use existing reconnect. Recheck ownership after ECHO; coalesce probes while upgrading queued/in-flight probes for forced settings reconnects. Actual methods/menu tests cover rejection, cancellation and both request orders. |
| #903/#904: Favorites feedback, default view and centered title | Indexed removal cleared the source star before persistence; failed source toggles still played success/reloaded; new Favorites opened on PS2 only; stars followed the title. | Return the actual removal result before clearing the star; render saving/success/failure feedback independently of courtesy notices and only confirm/reload successful writes. New configs open All while remembered shelves still win. Preserve centered title anchors with symmetric room and a leading star; ordinary lists use a fixed leading column. Execute actual C++ actions/removal/config decoding/toast timing/layout with fault injection and clock-wrap coverage. This changes UI commit ordering, not disk atomicity: PR #31 subsequently handles short transfers and close failures; truncating replacement and interruption recovery remain open. |
| #922: NIC reservation, DEV9 gates and IP-conflict notice | Existing RA menu methods could start SMB before selected UDP modules loaded; three UDP chains ignored DEV9 failure; no IP-clash query/notice. | Keep `Ranet` and `BdmSupport` methods, reserve selected UDP protocols only for menu actions, propagate DEV9 usability and balance failed references in Files/on-demand/boot paths. Append ministack export slot 7 and ioman devctl; queue one IO-thread notice for the GUI hook. Compile the actual C++ guards/refcount/notice and actual ARP handler in regressions. Newer RA browser/Caduceus absent; legacy Makefile/filter changes inapplicable to this SDK/edition CI. |
| #904: UDPFS operation serialization | Filesystem RPC callers and watchdog discovery shared one transport without a semaphore; teardown left the watchdog alive. | Serialize all operations that touch transport/FD state with the watchdog, stop it before teardown, retain 64-bit seek results and unlocked interrupt completion. Favorites and POPS adaptations are recorded separately in this table. |
| #904/#909: POPS UDPFS launch/config and rollback | UDPFS listed Ember only, lacked a POPSTARTER network driver/config editor and probed unsupported UL files. | Adapt to C++ source classes and host UI services; validate every live USB config before teardown, equip/verify the pinned Alpha pair, preserve configs/recovery backups on failed multi-volume replacement, retain partial-scan retry and avoid UDPFS UL probes. Propagate destination close errors and preserve last-good lists on output allocation failure. Official driver/config/license bytes and launch/rollback failures have host coverage; hardware acceptance remains open. |
| #908: cumulative ACK validation | Filesystem used the sequence helper; IMG still used the ineffective signed comparison after a 12-bit mask. | Both modes use the same sequence helper, including wrap and ambiguous half-ring behavior. |
| #913: canonical transport | The core was identical in both variants, while ACK behavior had already diverged. | Move the unchanged core and updated transport to `udpfs_shared/src`; retain per-variant wrappers, headers, defines, imports, module names and SDK targets. |
| #921: reconnect, stale ACK and discovery ARP | Reconnect retained dead-session counters; Files retried on stale ACKs; discovery did not announce the PS2 address. | Reset TX/RX state on successful discovery; keep waiting on the same alarm after stale ACKs in both send APIs; announce IP/MAC before bound broadcasts, excluding udptty and unicast. |
| #907 and #909: preserve existing VMC saves | A resize request unlinked the old image before asynchronous creation. An open error could start a truncating create against an unreadable image. | Port into `sysvmc.cpp`: explicit Delete is required to replace any existing different-size image, including malformed files. Prove absence with a completed directory scan, reject truncated paths, and propagate create submission errors to the dialog. Existing same-size images remain untouched. The POPS UDPFS config rollback portion of #909 is adapted separately below. |
| #910: image cache construction | The C++ class checked its own allocation but dereferenced failed prefix, suffix or entry allocations and accepted invalid counts. | Keep placement construction and private fields; validate counts and suffix, release all partially allocated fields and destroy the partial C++ object on failure. Compile the constructor with the actual class declaration in the allocation test. |
| #912: menu and art index allocation | Page, row and hint allocations were unchecked. Theme changes could publish a half-allocated ID/UID pair. | Check all allocations, unlock on failed page insertion, and replace both art arrays together. On failure discard the old theme's arrays to prevent indexing them with a new theme size. |
| #914: queue snapshot and append lifetime | `IoQueue::pendingCount()` read its head before taking its semaphore. Failed GUI appends overwrote navigation pointers with NULL. | Lock before reading the C++ queue head; keep tail, cursor, page start and autostart state on failed append. The legacy `submenuRemoveItem` routine is absent from this branch, so its backlink fix is not applicable. |
| #915: BDM private allocation | Failed per-slot allocation could register a page with NULL private data; settings re-apply never retried it. | Allocate at the registration boundary, hide/disable failed slots, retry later, and fail closed in init/cleanup/VMC/prefix callbacks. Retain `BdmSource`, template lookup, host services and identified-page retention. Skip NULL/empty app prefixes. |
| #911: IOP reset packet and failure handling | Unbounded outbound copies, unchecked intercepted lengths and a failed IOP heap allocation could corrupt memory or DMA to zero. The MIPS trampoline forced success. | Validate packet/payload/suffix capacities, reject oversized outbound commands, stop on failed allocation, unwind services and counters, prevent ELF loading after failed reset, and preserve C's return value through the assembly trampoline. Standard and RA lifecycle tests execute the production routines. |
| #906: RA Mode 6 snapshots (partial) | Mode 6 skipped the IGR handler that drove RA snapshots. | Add the RA-only snapshot handler after successful, telemetry-ready reset; failed interrupt registration remains retryable and repeated installation is idempotent. The older RA runtime has no `IGR_RequestReset` client command, so that part requires the broader RA runtime migration. The edition overlay now builds/packages RA as well as standard kits; runtime parity and hardware acceptance remain open. |

SDK adaptations retain `u32` for IOP `WaitEventFlag` outputs and add the thread
imports required by filesystem teardown. The C++ `GameSource` implementation,
protocol selector, network ownership and EE launch flow are retained.

Regression tests compile the production transport through each SDK target's
wrapper, feature defines and include paths. They exercise timeout/retry limits,
stale ACKs, both send APIs, reconnect sequence state, ACK wrap, actual ARP packet
fields and announcement order, plus filesystem operation overlap and error
unlock. The saved pre-port transports and discovery implementation fail these
same regression scenarios. Both GCC and LLVM builds are required.

Real-console acceptance remains open: server unavailable at boot, late server
startup, server restart/settings changes, Files and IMG modes, sustained reads,
Ember handoff, and normal SMB/UDPBD selection. Host tests and SDK builds do not
prove loss tolerance, performance, driver teardown safety on hardware, or full
public feature parity.

## Remaining migration work

The runtime-budget continuation refreshes production to
`c5800e4ff026018c6bd10cca64fc2720a0e9eaad`, including new QA credits and preserved
RE4/VMC/IGR evidence. Those docs/credits and prior diagnostics remain unadapted.
Current branch coordinates 4,096 entries/128 nodes, nine parts, 20 KB transfer,
validated set-sized protected storage and one/two/three-frame cadence through
C++ LaunchServices. See RA-RUNTIME-BUDGETS.md and issue #20 for validation.
Earlier notes to raise these budgets are superseded by this implementation;
newer timing/client/peer/overlay/browser/ORBIT/HTTPS behavior remains missing.

Latest refresh: production `6a3f12f2d22dbbf95bf2a1cf18f914ad6ed66145` includes
merged freeze diagnostics #942 and About/QA layout #944. They remain unadapted.
The current RA transfer batch adapts original `f0943360`'s exact fixed-stride
coverage checks, rejects parser-refused lists before persistence and fixes
binary-separator consumption (original #946). Actual C++ transfer tests and
all 62 Python/HTTP/seven C++ host suites pass; native/CI/package checks are
pending. Full RA/HTTPS/browser/client/ORBIT and peer verification remain open.
The existing 16 KB network-list ceiling is deliberately retained pending a
coordinated runtime/watch/snapshot budget port.

VMC automatic format validation is merged in #38 at `3acd135c`; its final
compiler/host/32-configuration/three-kit checks and all 35 final package checks
pass. Earlier statements below that this is unresolved in C++ are historical.

The latest source audit is pinned to `fb00066fe7c806a415cd019177bcf0227068bf52`,
including original #938/#939/#940 repairs of reported #934/#935/#936.
Merged #932 adds optional CFG list titles; #937 updates the original Pages guide.
Open original #733 (cover art flow, head `35653d79484e70b65024e972352e0718c1a48626`)
and #687 (DO NOT MERGE, head `dba97ff725ac4dbca22c1f69ccb40443e03e696e`)
remain tracked separately from production. Newer RA/browser changes
#923/#926/#927/#929/#930 are still outside the individual ports above.

| Area | Evidence and next boundary |
| --- | --- |
| POPS UDPFS and Favorites storage recovery | Favorites feedback/view/title changes are adapted above. Public #904/#909 POPS UDPFS launch, driver preparation and rollback are adapted in the current branch. The UL follow-up reproduces and fixes a trailing-record heap overwrite, accumulates partial reads and retains cached state on malformed/failed reads; its real-layout regression runs under ASan/UBSan and fails on the pre-fix scanner. Verify final compiler/edition CI and console acceptance; interruption recovery remains separate. PR #31 handles short transfers and close failures. Implement interruption-safe replacement/recovery across supported devices; the upstream in-place writer is not atomic. |
| RA runtime and standard/RA isolation | Public #894/#899/#906/#916/#923 include newer RA runtime/browser/client behavior and ORBIT handoff. Only the snapshot subset of #906 is covered here. Require explicit standard/RA targets, package isolation and launch/resource validation before claiming RA parity. |
| Configuration matrix and release packaging | Three complete ps2build edition kits pass CI. The recovered PADEMU-disabled, DS5/extras, DTL, diagnostic, debug and UART definitions are adapted through the edition builder with isolated configuration stages and release rejection guards. PR #24 passed all 32 GCC/LLVM configuration builds and artifact verification. No-IGR is runtime Mode 6 (`0x20`), whose current hook gates and host reset/snapshot tests agree with production; no separate compile-time flavour was found. DECI2, language/font/debug distribution bundles and publication remain open. Keep three release channels and one SDK. |
| Existing feature PRs | #17/#18/#19/#21/#22/#23/#24 are merged. #21 retained the useful Ember, Neutrino, docs/evidence, splash and updater work from #12–#16; those originals are closed as superseded. Exact CI/artifact refs and local recovery are recorded in the checkpoint. |
| Earlier feature/config parity | #885/#887/#889/#898, automatic VMC and newer Ember missing-core behavior are merged and verified through final integration `39eda4b8`. Remaining UI/font/settings changes require individual body-level comparisons. PR titles or test-count differences alone do not establish parity. |
| Optional CFG list titles (#932) | Adapted to C++ cache and GameSource with default-off setting, title sorting, RA prefix preservation and worker refresh. Merged in PR #32, final compiler/host/32-configuration/three-kit CI and downloaded artifact checks pass at `cd787705`. Pages #33 and Wiki guidance are published. Console acceptance remains open. |
| CJK and game-type labels | Current C++ font code decodes UTF-8 but lacks #917 independent CJK face/glyph fallback (original `5aa89ab0`; the allocation guard from `b995cf24` already exists in the C++ FontSystem). The separate `game_type_labels` setting is also absent; VCD ID hiding and startup captions do not implement it. Preserve both as explicit UI gaps. |
| VMC #939/#940 follow-ups | PR #34 releases the abort lock before cluster IO, preserves failed-seek/short-write handling, follows effective loader policy, waits for slow working jobs, bounds cancel cleanup and re-probes created cards. It re-resolves Favorites and validates source/row identity after yielding. Real-source regressions, native LLVM and final compiler/host/configuration/kit checks pass at `01affe4d`. Full-size failed-format retry is a separate shared defect reported as original #941, still unresolved here. |
| Favorites #938/#940 staged recovery | Merged PR #36 at `9a868e82` adapts bounded image reads, complete-primary precedence, native recovery-only restore-before-restaging and exact staged/primary readback through existing C++ storage helpers. IO/unknown-version/oversized stores remain read-only. Original #943 proves the ENOSPC overwrite fallback loses the last complete copy; this port refuses that edit instead. Host/native/final GCC/LLVM, 32 configurations and three kits pass; all 35 final packages verify. Device/power-loss acceptance remains pending. |
| Failed-format VMC retry (original #941) | Current branch adds read-only header/geometry validation through GameSource before automatic reuse and after creation. Full-size erased images and IO failures refuse assignment; valid formatted Neutrino odd-size cards remain eligible. No implicit deletion/reformatting. Actual-source regression fails on the old probe and passes with seek/read/close/overflow faults. Host suites pass; native/CI/package and physical-device acceptance remain pending. |
| IGR pad-buffer lifetime (original #951) | Adapt the open candidate's buffer invalidation before intercepted reset, state-preserving reinstall and interrupt-state-preserving pad publication. This branch retains VBLANK input handling rather than importing the upstream polling worker. Standard/RA actual-function regressions cover stale buffers, libpad layouts, pending state and failed resets. Source-backed defect; target/review/console evidence remains separate, and no RE4 causal claim is made. |
| Coverflow page animation (original #952) | Adapted to actual C++ page methods with changed-selection gating, both wraps and unchanged flat-theme/page targets. Sanitizer regression exercises real methods and fails on the pre-port source. Target/package and console evidence remain separate. |
| Fresh-start guide (original #953) | README/theme claims corrected and DEFAULTS.md added for verified C++ values. Runtime differences remain open: widescreen/audio on and center scale 30 versus original 4:3/audio off/scale 45. No silent default changes or full-default-parity claim. |
| Hardware acceptance | Validate boot, USB/MX4SIO/MMCE/ATA discovery, hotplug, device allocation recovery, existing VMC handling, game launch/IGR, Files/IMG reconnect and other network protocols. LLVM floating-point behavior/performance also remains unproven. |

The new regression tests execute the adapted C++ allocation, queue and GUI
paths, plus standard/RA reset and snapshot handler variants. Standard and RA
builds/packages pass; hardware and full RA behavior remain separate gates.
