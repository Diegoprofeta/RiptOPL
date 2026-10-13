# RiptOPL SDK/C++ migration checkpoint

## Current continuation: older feature parity and released SDK follow-up

Base is merged POPS PR #25, `4157d5a23eb51d377635188b811b74883e927e41`.
Its fresh compiler, host, 32-configuration and three-kit integration runs and
downloaded artifacts pass. Pages PR #26 deployed at `fdda817f`; Wiki `6c1ffb6d`
updates only POPS sections, preserving unrelated imports and credits.

Continue `codex/legacy-parity-885-898`. Adapted production bodies are #885 quoted
config decoding (`f71cb5c6`), #887 top-level Ember image filtering (`ac5085c9`),
#889 VMC write/semaphore recovery and Neutrino warning policy (`3e836bd3`), and
#898 explicit SMB session checking (`2297297b`). The current production snapshot
is `a0ca55c54cb32b801423a4fdc800968ff4f62c2d`; full RA/browser parity is separate.

The C++ config sanitizer suite tests real file save/read cycles, maximum escaped
values and unknown escapes. Config and VMC regressions fail on the actual
pre-port source. VMC creation also stops before writing on a failed seek and
releases the semaphore. The stronger existing non-destructive VMC guards stay.
The production automatic-VMC-creation launch hook is absent here; this batch
does not claim that broader feature is ported.

Checked SMB Refresh uses `EthSupport`, host library services and the existing
serialized reconnect path. Healthy ART/BGM handles stay open. Queue rejection
is retryable; protocol changes cancel queued/in-flight probes. A settings
reconnect upgrades a queued or in-flight probe instead of being lost behind it;
the initial adaptation failed that scenario and the corrected regression passes.
New checks execute the actual class methods, menu dispatch and Ember scan.
The seven C++ sanitizer suites are now explicitly included in CI.

Runtime checkpoint `47f61dce` is pushed. Local ps2build/sdk-world are updated to
`v2026.10.12.2`, LLVM to `v0.3.3`; sdk-core remains `v2026.10.12.1`.
The released project-header fix passes a native header-only-change probe on
GCC and LLVM: both rebuild the object with changed bytes and project `-I` paths,
without the old `-sys-header-deps` workaround. The wrapper now requires the fixed
ps2build release. Both compiler package sets contain native `ppctty` (AFL-2.0);
UART overlays use that package and the bundled driver source is removed while
retaining license/provenance notices. Retain the RA socket compatibility archive:
released cglue still lacks those APIs, as the maintainer confirms.
The EE-core stack guard and narrow LLVM IGS `-Oz` policy remain unchanged.
All 57 Python host suites, HTTP and seven C++ sanitizer suites pass after the
final changes. Native LLVM Korium `debug_uart` compiles, links and packs with
the SDK driver (ELF SHA256 `62bf8defbff72e07c1681a959b0f1667bd5e401144223f366fc2ec69ec9cea8f`).
This local candidate records a dirty SDK-cleanup checkout; clean final CI,
configuration/kit verification and console UART acceptance remain pending.

## Latest continuation: POPS UDPFS #904/#909

Base integration is merged PR #24, `7bcb77b3ccf5bcf2af29c34527d864a6417ffbc7`.
Its fresh GCC/LLVM, host, format, 32 optional-configuration builds and three
standard kits pass. All 32 configuration candidates and three downloaded kits
were independently verified. Historical continuation instructions below are superseded.

Continue `codex/pops-udpfs-parity`. Production was fetched at
`90566eb863f9ed3771cdbc9702a5611b55f8ddd9`; #904 POPS and #909 rollback are
adapted through `UdpfsSource`, `VcdSupport` and host UI services. UDPFS Files
merges VCD/Ember rows; partial PS1 scans and failed ISO scans stay retryable.
ISO-only scans avoid unsupported UL probing. Output allocation failure keeps
the last-good library. Launch validates USB configs, remote VCD readability,
POPSTARTER lookup, equipped driver identity and clean-launch eligibility before
teardown. Both page and Favorites use the same virtual launch method.

The editor stages both DAT files on every identified USB volume, backs up old
copies, rolls back failed replacement, and preserves recovery files if restore
fails. Copy/write helpers propagate destination close errors. These checks do
not establish power-loss atomicity across multiple files or USB volumes.

The official BDM-UDPFS Assault Alpha archive has SHA256
`532bcf85b5beff90df9ff51da02b690b0bdee82ed3372e40b4f2c36de5eaf5ce`.
All ten upstream driver/config/notice members match byte-for-byte; provenance
and full notices ship in `POPS/UDPFS-NOTICES/`. USB supplies non-VCD dependencies;
no dummy local VCD is required. This external POPSTARTER driver is separate
from the sole ps2build SDK and the Neutrino PS2 network loader.

All 55 Python host checks, HTTP and seven C++ sanitizer suites pass, including
121 config/rollback/module checks and actual C++ launch/scan/IO failure harnesses.
The native LLVM Korium compile/link/pack passes. New PR compiler/configuration/
edition CI and downloaded artifact verification must finish before merging.
Physical-console POPS UDPFS acceptance, RA runtime parity
(including newer production #923), Favorites durable
storage, DECI2/distribution bundles and publication remain in issue #20.

The follow-up UL audit reproduced a heap-buffer-overflow with a 65-byte `ul.cfg`:
the old loop allocated one 64-byte record's output but wrote a second row for
the trailing byte. The real-layout ASan/UBSan regression fails against the
pre-fix scanner and passes after enforcing record alignment, bounded output
counts and complete reads. Valid partial reads accumulate; failed size/read/
close/allocation checks retain the previous list/count/size. Valid UL, ISO and
folder rows still publish together. Corrupt UL content now prevents replacement
of the cached library, rather than publishing partially trusted entries.

The first configuration matrix passed 31/32; the remaining job timed out reading
Vorbis release metadata from `git.techwritescode.dev` after 60 seconds, before
compilation. `tools/install_ports.py` now retries transient network/HTTP failures
up to three times, reports the URL, and still fails immediately for permanent
HTTP errors. Package selection, staged replacement and archive checks remain.
Fault injection covers interrupted response reads, transient HTTP errors,
permanent missing releases and retry exhaustion. Reverify the final pushed head.

## Latest continuation: optional ps2build configurations

Integration `daae402eb7e3618c0de948a2537a3ae4b4a4d960` contains merged PR #23
Favorites parity. Fresh GCC/LLVM, host, format and all three full-kit jobs pass;
downloaded final integration kits pass independent publisher verification at
that exact SHA. Both primary local RiptOPL checkouts were synchronized and clean.
No releases were published. The earlier sections below retain historical evidence;
their instructions to continue the already merged branches are superseded here.

Continue `codex/ps2build-configurations`. It adapts the recovered transition
definitions through `tools/build_edition.py --configuration`, retaining the
three editions and one SDK. See [BUILD-CONFIGURATIONS.md](BUILD-CONFIGURATIONS.md)
for flags, paths and limits. All 14 configurations preserve edition/RA ABI in
host checks; the new workflow builds 16 selected edition/configuration pairs on
both compilers (32 candidates). Nonstandard objects/stages are isolated, and
packaging/publication reject nonstandard manifests. Older standard manifests
remain verifiable. Do not restore the recovered helper's duplicate RA setup,
obsolete asset paths, or alternate release workflow.

The native LLVM Korium `iopcore_debug_uart` compile/link/pack passes, as do all
52 Python host suites, HTTP and seven C++ sanitizer suites. Verify the new PR's
exact-head 32-build matrix and standard edition packages before merging.
PPC TTY is still absent from SDK package discovery; its six recovered source/
license files were compared to official ps2sdk `ac92a9f657d2e531dd8f060250b07f2a5ac6dea5`
and match after line-ending normalization. License/provenance remain in the
source and applicable candidate artifacts. UART output requires separate console
acceptance. The source contains no verified compile-time no-IGR switch; that
audit, DECI2 and debug/language/font distribution bundles remain in issue #20.

## Latest continuation: merged network port and Favorites #903/#904

Verified integration is `d54dfc57d6af99995e72568af7a7ae8323b7dec8` (PR #22).
Fresh [GCC/LLVM](https://github.com/NathanNeurotic/RiptOPL/actions/runs/38331420380),
[host gates](https://github.com/NathanNeurotic/RiptOPL/actions/runs/38331420445),
format and [three complete kits](https://github.com/NathanNeurotic/RiptOPL/actions/runs/38331420407)
pass. Downloaded integration artifacts independently pass
`python tools/publish_editions.py build/ci-integration-d54dfc57 --check` at that
exact SHA. PR candidates were verified separately, without relabelling them.
No GitHub releases were published; console acceptance remains open.

Continue `codex/favorites-parity-903`: production #903 (`a73fb2e4`) and #904
(`906cdafe`) Favorites changes are adapted to the C++ classes. Indexed removal
returns persistence failure before clearing the source star; source and Favorites
actions show saving/success/failure feedback and only confirm/reload successful
writes. A new config opens Favorites on All; existing valid shelves remain.
Centered titles retain their anchor and scrolling room with leading stars;
ordinary lists retain aligned leading columns. Language labels are appended.
Regression coverage executes the actual C++ removal, R3 actions/guards, config
decoding, wrap-safe toast timing and layout geometry. The host entry point is
`.github/scripts/test_favorites_parity.py`; the full suite is
`sh tools/run_tests.sh -k`. Refresh the branch's exact compiler/edition CI before
merging. Local host/native logs are ignored under `build/`.

The inherited Favorites writer still opens with `O_TRUNC`, writes once and
ignores `close` errors. This port fixes feedback/star ordering, not atomic disk
replacement. Partial writes, interrupted saves and device-specific recovery need
a separate implementation and fault-injection/hardware checks. POPS UDPFS
launch/config/driver work and full RA/ORBIT parity remain in issue #20.

SDK feedback was sent to [@techwritescode on PR #22](https://github.com/NathanNeurotic/RiptOPL/pull/22#issuecomment-6135955069):
LLVM project-header dependency tracking, the confirmed missing POSIX socket
entrypoints in both installed cglue archives, and unavailable PPC TTY package
discovery. Local asset regeneration is an application preparation issue, not an
SDK defect. Retain the current RA-only compatibility code until native SDK
coverage preserves libc descriptor ownership and passes runtime validation.

The recovery section below records the earlier checkpoint; its open-branch
directions are superseded by this section. Recovery ZIPs and permanent Git refs
remain intact.

## Local recovery and production #922 (prior checkpoint)

Integration is `6988499b84e6049c7f544e4a8eff2769f58563a3`: PR #21 merged the
useful changes from #12–#16, and those originals are closed as superseded.
Its GCC/LLVM, host and three-edition CI passed. Independently downloaded kits
passed publisher verification against that exact integration SHA. Site
`72e3dd6575c0ff602cf087e1c7b812428984c2b8` and wiki
`45e0ee19293b1f86a4bbd599671700b838d86a89` are pushed and validated.

Continue branch `codex/network-parity-922` for the next reviewed batch. It
adapts production `0a1a593ade393d2c1d28bafb09ea8f3c5cb63706`: DEV9 return/failure
gates in all three UDP load paths, selected UDP NIC reservation for the existing
C++ RA menu methods, appended ministack export slot 7, local IOP devctl and a
one-shot warning queued by the IO scan and displayed by the GUI frame hook.
The newer achievements browser/Caduceus methods are absent and remain part of
the broader RA port. Legacy Makefile dependencies and RA-only preview filtering
were not imported; ps2build header tracking and all-three-edition CI remain.

Local ps2build/SDK update commands report `v2026.10.12.1` current, optional
LLVM `v0.3.2` current (clang 24.0.0git). Regenerating assets with
`python tools/assets.py all` fixed stale language IDs in the older local build
outputs. The actual LLVM compile/link/pack then passed. Console compatibility
and LLVM precision/performance are still unverified.

Local cleanup preserved changes before stashing them. Recovery ZIPs and JSON
hash inventories are under `REA/local-recovery/2026-10-12/`, outside the source
clone. All archived file bytes were read back and verified before stashing.
The old repository also retains permanent recovery refs:

- `refs/recovery/2026-10-12-public-transition` →
  `6aabfb2bac319d4d45fd9a2ec610bacf2d66fa99` (112 files, including old variant helpers).
- `refs/recovery/2026-10-12-primary` →
  `d76f7e5bc164cb7f166815308490713d5ea18962` (old primary artwork and scratch scripts).

Three entirely clean closed-PR worktrees (docs, Ember Watch and site) were
removed; their Git branches/history remain. Three fully merged local branches
in the active clone were deleted. The transition, Neutrino and unrelated Copilot
worktrees were retained, including ignored build outputs and the nested legacy
wiki checkout. Recover unique `tools/build_flavour.py`, variant tests and PPC
TTY provenance from the ZIP or the transition stash's third parent before
implementing configuration coverage. Never restore obsolete workflows wholesale.

The historical sections below retain prior evidence; their open-PR and dirty
worktree descriptions are superseded by this continuation record. Issue #20
remains authoritative for unfinished parity, publication and hardware work.

## Current merged checkpoint and continuation queue

The authoritative remaining-work tracker is
[issue #20](https://github.com/NathanNeurotic/RiptOPL/issues/20). Start there and
refresh the integration head before continuing. PR #19 merged to `rebuild/main`
as `0dae12553672d8c988fe5b038d383e375d287eff`, after PR #18. Its exact PR head
`c53341a02f74102d6abcf68f50910ac87f46e98f` passed GCC/LLVM, host, format and all
three complete edition package jobs. Downloaded packages independently passed
publisher verification against GitHub's PR merge revision
`b6af86efd7a2e8dc0518048edd4d12e4175e3781`; the final merge has the same tree.
Fresh integration CI also passed at `0dae1255`. These are separate source
revisions; do not relabel the PR candidate as a final integration artifact.

Korium, RetroAchievements and IncebtIon now have complete ps2build-only release
candidate workflows. No GitHub releases were published during this work;
publication remains an explicit dispatch from the tested integration head.
The RA edition builds and packages, but newer RA/ORBIT behavior and console
acceptance are still outstanding. The socket compatibility source is a small
RA-only fallback inside ps2build, not a second SDK.

PR #17 merged the full production site history as
`acdb961d8c36a2da33f3a7c8593db378d2feb248`; GitHub Pages reports a successful
deployment. All 33 HTML pages and 1,669 local links/resources pass validation;
the generated search index is current. The separate wiki import preserves the
production history and destination initialization at
`50a4053a267295977d3c146f82450b5f19a1364a`, with 53 content pages plus sidebar
and footer and 651 verified internal links/anchors. The imported guides retain
their production evidence and explicitly qualify migration/hardware coverage.

The follow-up branch `codex/merge-migration-queue` consolidates useful work from
the older PRs: #13 Ember saves (`e5ff4ae0`), #14 Neutrino editing/preflight
(`ffc9867a`), #15 docs/evidence (`44661659`), #12 splash artwork (`4efe9d46`),
and #16 Ember Watch (`8f3f02bf`). It retains the newer warning parser, VMC strings,
edition texture ordering and release contract. Ember Watch builds all three
candidates with `publish=false`; it does not invoke removed Korium automation.
All combined host tests, HTTP tests and seven sanitizer suites pass locally.
The consolidated PR's checks and actual merge state determine its final status.

Production advanced to `9d910fc05796b7bcfb4f00544a55baf73d800a33`, adding #922
NIC reservation/DEV9/IP-clash hardening after the original ledger audit. That
port remains open in issue #20 along with Favorites/POPS UDPFS, full RA/ORBIT,
additional configurations, language packages, publication and console testing.
Other dirty worktrees are preserved; the public-transition worktree contains
useful uncommitted variant work and must be inspected before duplicating it.

The following sections retain the earlier build and artifact evidence for
provenance; their older PR/setup status is superseded by this checkpoint.

This is a continuation record, not a declaration of full public parity or console
acceptance. Read this and `UPSTREAM-PARITY-2026-10-12.md` before repeating setup or
starting another port. RiptOPL was made public during this session; GitHub's API
now reports `visibility: public`. Earlier notes call it the private migration repo.

## Repository and branch

- Migration: `NathanNeurotic/RiptOPL`, local checkout
  `C:\Users\natha\Github\REA\RiptOPL`, branch `codex/sdk-llvm-parity`.
- Production reference: `NathanNeurotic/Open-PS2-Loader`, default `rebuild/main`.
  Do not confuse it with the migration repository or change that checkout as part
  of this work.
- Continue [PR #19](https://github.com/NathanNeurotic/RiptOPL/pull/19), stacked on
  [PR #18](https://github.com/NathanNeurotic/RiptOPL/pull/18), base
  `rebuild/main` after PR #18 merged as `7a760cf9c1d45cbca9c6cc9a7df86dced221ad41`.
  Refresh remote refs and actual reviews before updating or retargeting it.
  `techwritescode` is the requested reviewer; no submitted reviews were present.
- Other local migration checkouts/worktrees contain unrelated uncommitted work.
  Preserve them, especially `.codex\worktrees\public-transition\RiptOPL`.

## Committed work

| Commit | Scope |
| --- | --- |
| `c7495a366fa4faa4eceaad6240adc9eabe8e0d7d` | Native Windows assets, compiler-qualified ports installation, warning reporting and GCC/LLVM CI setup. |
| `988d4ac87911183394d711cb26bd78497f5a72ae` | LLVM project-header dependencies through `tools/build.py`. |
| `fb50211e1eb9eae2d6c507cf55707078ecd5ecc8` | Public UDPFS serialization, shared transport, reconnect/ACK/ARP fixes, with production driver regressions. |
| `f2a37033a05f2459517e431c6a40f3656ec74a4e` | VMC preservation, BDM allocation retry, C++ cache/menu allocation handling, queue/GUI lifetime, reset packet/failure handling, and the RA Mode 6 snapshot subset. Eight new regression files; CI and parity ledger expanded. |

The checkpoint commit itself only adds this document. The locally built source
commit is `f2a37033a05f2459517e431c6a40f3656ec74a4e`; do not relabel its artifacts
as a later commit's build. Future source changes need new builds and versioning.

## Reproduce the build and tests

Installed locally: ps2build/sdk-core/sdk-world `v2026.10.12.1`, optional
LLVM toolchain `v0.3.2`, GCC toolchain `v2026.09.27`. SDK root:
`C:\Users\natha\AppData\Local\ps2build`. The global ps2build MCP is registered;
the CLI was used for these native Windows builds. The default SDK update does
not install LLVM automatically.

```sh
ps2build update
ps2build update llvm-toolchain
python tools/install_ports.py --toolchain all
python tools/assets.py all
python tools/build.py --toolchain gcc --out-dir build/gcc
python tools/build.py --toolchain llvm --out-dir build/llvm
```

Use `python3` on hosts that require it. Use `tools/build.py` for LLVM: direct
SDK builds currently omit project headers from dependency tracking. GCC and LLVM
outputs/ports stay separate. Generate `tools/assets.py version` after committing
source, then build both sequentially; building both concurrently causes heavy
resource contention on this host.

Host tests on Linux/WSL: `sh tools/run_tests.sh -k`. The local WSL virtualenv
`build/site-test-env/bin` has PyYAML, Beautiful Soup and markdown-it-py; put it
first on PATH so the site test runs. No PS2 compiler is needed for host tests.
Native Windows assets require Git for Windows, Python/PyYAML and the SDK.

## Validation and local artifacts

- All **46** `.github/scripts/test_*.py` files, HTTP parser tests and **7** existing
  ASan/UBSan C++ suites passed without skips. New tests compile the adapted
  production C++/C routines, including standard and RA reset/handler variants.
- Saved pre-port sources reproduce image-constructor crashes, invalid BDM
  registration and the queue-head lifetime regression. The old VMC implementation
  fails the preservation/bounds scenarios. New code passes. Reset/Mode 6 source
  and lifecycle checks also detect the missing pre-port implementation.
- Both native Windows compilers compiled all EE sources, linked and packed the
  main flavour with version `v1.2.0-Beta-3512-f2a3703`. Unchanged IOP objects were
  validated in the earlier full/UDPFS builds. This is not a fresh clean rebuild
  of every IOP module at the final commit.
- Final GCC warning gate: **55** against baseline **62**, zero regressions; the
  baseline was not changed. Coupling gate, clang-format 12, workflow syntax,
  Python syntax and whitespace checks passed.
- Both dependency databases contain the version header and canonical UDPFS
  sources; touching the version header schedules compilation in both compilers.
- LLVM's Windows linker crashed once in its winpthreads thread pool with
  `0xC0000008`. An unchanged retry and the final versioned link passed. This is
  an intermittent SDK tool failure, not a confirmed fix. Logs are retained.

Local candidate: `dist/sdk-f2a3703.zip` (12 files, CRC checked). It contains two
packed alternatives, a JSON manifest, current/prior build logs, generated Ninja
graphs and the LLVM failure/retry logs. `dist/` and `build/` are intentionally
ignored; these local files are not a published release.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `RiptOPL-main-gcc-f2a3703.elf` | 1,650,496 | `1f7c8a8c51155cbbf49c2574bbac76257fa522f8195c1d19c6d4d98013e2a9cc` |
| `RiptOPL-main-llvm-f2a3703.elf` | 1,696,032 | `311a82f9739a6e278eaa7830f43016793179817f157d6b7d9d9d37a978b84d22` |

Before the visibility change, Actions jobs never started because of account
billing/spending limits. New public-repository CI must be checked at its actual
head; old failed runs are not compiler failures. Do not infer a green run from
this checkpoint or from the repository visibility alone.

## Continue from here

1. Read issue #20, refresh `rebuild/main`, and inspect the consolidated queue
   PR's exact head, reviews, CI and merge state. PR #19 is already merged.
2. Audit and adapt public Favorites/POPS UDPFS (#903/#904 plus #909 rollback) as
   a coherent source/launch/config/package change. Preserve `GameSource` and host
   services; do not replace converted backends with legacy C files.
3. Reuse the committed queue consolidation before duplicating PRs #12–#16.
   The full site and wiki imports are published; PR #17 is merged.
4. Validate the three ps2build release editions and standard/RA package isolation, then port
   the remaining RA runtime/browser/client/ORBIT behavior. The current
   `tools/build_edition.py` now overlays the base `ps2.yaml` for Korium, RA and
   IncebtIon. Clean edition CI builds and complete packages now pass;
   runtime/hardware parity remains a separate gate. `IGR_RequestReset`
   is absent from the older private runtime.
5. The release workflow now uses only ps2build and builds three complete kits.
   Publication is explicit manual dispatch; validate staged packages, provenance
   and all exact-head CI jobs before publishing. Old normalizer/promote/Korium
   branch-sync publishers are removed to prevent conflicting release contracts.
   See `ROLLING_RELEASE.md`. README badges and full Pages/wiki imports are done;
   keep their generated content and migration-status claims synchronized.
6. Work through earlier feature/config differences and console acceptance in
   the parity ledger. LLVM ignores `-fsingle-precision-constant`; precision,
   performance, audio, storage/network behavior and game/IGR compatibility need
   hardware evidence.

Keep committing verified batches and update this continuation record when a
material state changes. Preserve the distinction between source tests, compiled
ELFs, packaged artifacts, GitHub CI and real-console acceptance.
