# Private SDK migration: public parity ledger

This ledger records verified ports into the C++/ps2build repository. It does not
claim that the entire public repository is synchronized. The public source
snapshot used for this UDPFS slice is Open-PS2-Loader commit
`6d04b40e8d857368110265a18ec9fc90b7c316c4`.

| Public change | Private state before this port | Port and scope |
| --- | --- | --- |
| #904: UDPFS operation serialization | Filesystem RPC callers and watchdog discovery shared one transport without a semaphore; teardown left the watchdog alive. | Serialize all operations that touch transport/FD state with the watchdog, stop it before teardown, retain 64-bit seek results and unlocked interrupt completion. Only the UDPFS portion of #904 is covered. Favorites and POPS changes remain separate. |
| #908: cumulative ACK validation | Filesystem used the sequence helper; IMG still used the ineffective signed comparison after a 12-bit mask. | Both modes use the same sequence helper, including wrap and ambiguous half-ring behavior. |
| #913: canonical transport | The core was identical in both variants, while ACK behavior had already diverged. | Move the unchanged core and updated transport to `udpfs_shared/src`; retain per-variant wrappers, headers, defines, imports, module names and SDK targets. |
| #921: reconnect, stale ACK and discovery ARP | Reconnect retained dead-session counters; Files retried on stale ACKs; discovery did not announce the PS2 address. | Reset TX/RX state on successful discovery; keep waiting on the same alarm after stale ACKs in both send APIs; announce IP/MAC before bound broadcasts, excluding udptty and unicast. |

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
public feature parity. Other newer storage, UI, RA and flavour changes still
need individual comparison and adaptation.
