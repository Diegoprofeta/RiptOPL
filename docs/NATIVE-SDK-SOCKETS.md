# Native ps2build sockets and audio

Builds now require **ps2build and sdk-core v2026.10.13 or newer**. Update the
installed SDK with `ps2build update`. Updating only the command-line executable
does not satisfy the core-package requirement; the build helper checks both
before invoking the compiler.

The released GCC and LLVM cglue archives supply `socket`, `bind`, `recvfrom`,
`sendto`, `setsockopt` and `select`. The RA edition uses those native entrypoints;
the `ps2sdk_socket_compat` archive is no longer generated or linked. Standard
editions still exclude the RA application sources/resources. GCC and LLVM use
their own installed package trees.

The SDK source checked for this transition is
[sdk-core v2026.10.13](https://git.techwritescode.dev/ps2/sdk-core/src/tag/v2026.10.13),
commit `c8283e7fe933aab65b4ecc48d39ce2f39bdb2886`. Its five relevant
`core/libcglue/src/socket.c` function bodies match the previously pinned fallback
after whitespace normalization. `glue.c` closes through the descriptor's close
callback and releases the libc descriptor; `F_SETFL` uses its nonblocking
callback. The native socket function uses that same descriptor table and
releases allocations when the registered socket callback fails. RA's per-call
`0x08` receive flag and existing NIC ownership policy are retained. Source and
notices for the retired fallback remain for historical/source attribution.

RiptOPL already uses the SDK's newer `audio` driver, embedded as `audio:audsrv`,
with the `audsrv-compat` client library. That package links the `audio` client
library and keeps the existing API. The separately released legacy audsrv
package is not the application's selected backend. No audio rewrite is needed
to consume the maintainer's deprecation notice.

Package symbols and source inspection establish the dependency boundary. Native
RA compile/link, GCC/LLVM CI and package verification remain separate checks;
RA discovery, repeated socket open/close, nonblocking receive, audio and
physical-console acceptance must still be tested on hardware before claiming
runtime parity. The broader RA/ORBIT port remains tracked in
[issue #20](https://github.com/NathanNeurotic/RiptOPL/issues/20).
