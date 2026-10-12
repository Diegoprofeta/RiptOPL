# SDK socket glue compatibility

Unmodified `ee/libcglue/src/socket.c` and `fdman.h` from [ps2dev/ps2sdk](https://github.com/ps2dev/ps2sdk), commit `ac92a9f657d2e531dd8f060250b07f2a5ac6dea5`. Original copyright headers and the Academic Free License 2.0 are retained. `UPSTREAM` records the exact source revision.

The rolling suite used for the native migration check (sdk-core v2026.09.29.1) omitted libcglue's socket wrappers. RA needs five POSIX calls. Its build compiles `socket`, `bind`, `recvfrom`, `sendto` and `setsockopt` into a separate archive, preserving libc's descriptor table, error handling, close and nonblocking behavior.

This fallback does not pin the SDK. All configurations use one rolling ps2build suite. The build manifest records its resolved component versions. Reassess the compatibility archive when the SDK supplies these functions itself.
