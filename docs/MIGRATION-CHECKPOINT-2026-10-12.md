# RiptOPL SDK/C++ migration checkpoint

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
