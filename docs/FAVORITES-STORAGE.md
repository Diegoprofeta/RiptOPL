# Favorites storage and failed edits

Favorites use the shared OPL configuration directory's `favourites.bin`. The
file format remains OFAV version 3, with read support for versions 1 and 2 and
complete uOPL/wOPL imports. The three ps2build editions use the same policy.

Adding or removing a favorite first reads the stored list. Only a genuinely
missing file (`ENOENT`) or a complete supported list permits an edit. A valid
header-only OFAV file is an editable empty list. A zero-byte file, truncated
record, invalid text terminator, unsupported version, oversized list, trailing
data, failed allocation, failed seek, read error or close error refuses the
edit. A salvageable prefix may still be displayed; it is never silently saved
over the original. Existing failure feedback reports the refused edit and
does not confirm it or change the source star.

Positive short reads and writes are accumulated. A write stops on an error or
zero progress, always closes an opened descriptor, and reports close errors as
save failures. A healthy save still writes the serialized image in one call.
No extra file opens, temporary files or rename requirements are introduced.

This does **not** provide durable replacement or power-loss recovery. The live
file is still opened with `O_TRUNC`; a later device failure can leave it partial.
Do not delete an unreadable file simply to make the next add succeed: first
copy it elsewhere and recover the missing entries or restore a known-good copy.
Device-compatible backup/replacement/recovery is tracked in
[migration issue #20](https://github.com/NathanNeurotic/RiptOPL/issues/20) and
[original issue #936](https://github.com/NathanNeurotic/Open-PS2-Loader/issues/936).

The source fault tests run the actual reader, writer and editing methods under
ASan/UBSan. They establish host behavior at each injected IO boundary; physical
memory-card, BDM, MMCE, HDD and network filesystem acceptance remains separate.
