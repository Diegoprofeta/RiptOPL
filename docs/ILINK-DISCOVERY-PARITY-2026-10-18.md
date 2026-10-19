# iLink discovery parity (2026-10-18)

Original Open-PS2-Loader PR #867 added a bounded root-readiness probe after block
device module loading. The reference `b35ff38c` contains it; migration integration
base `1c4822fc` does not. Restore that behavior in the C++ source without changing
launch arguments, compatibility modes, or game-side driver initialization.

The IO worker checks an enabled, loaded iLink transport once per enabled session.
An immediately ready root costs no sleep. An absent root costs at most twelve
250 ms waits. Every completed probe requests one device-generation refresh,
including immediate readiness and absence. Disabling iLink rearms the probe;
a module that has not loaded does not consume it. Existing mount events remain
responsible for arrivals after the deadline. The three-second bound applies to
the inserted waits; it is not a wall-clock guarantee for underlying filesystem IO.

The actual-source C++ host harness covers roots ready immediately, after two or
eleven waits, at the deadline, after the deadline, and never; it also checks
one-shot behavior, disabled state, missing module, subsequent module load, and
re-enable. This validates scheduling/refresh policy, not FireWire hardware.

An enabled absent iLink device can delay the IO worker by three seconds once per
session. This is the upstream discovery behavior being restored. It is not a
fix claim for FifthFox's native OPL launch failure or Neutrino mode changes.
The earlier community handoff also records intermittent iLink failures before
the migration. Track the current hardware investigation in issue #63; the
independent POPStarter shipped-size correction remains PR #64.

References:
- https://github.com/NathanNeurotic/Open-PS2-Loader/pull/867
- https://github.com/NathanNeurotic/Open-PS2-Loader/pull/824
- https://github.com/NathanNeurotic/RiptOPL/issues/63
