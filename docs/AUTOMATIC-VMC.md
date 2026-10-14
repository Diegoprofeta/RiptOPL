# Automatic VMC creation

In **Settings → Game Launching**, enable **Create VMC on First Launch** to create
and assign an 8 MB card when a PS2 game's slot 1 has no card assigned. The option
defaults off and is saved as `auto_create_vmc`. It applies to menu launches,
including PS2 Favorites, on all three ps2build editions. It does not change
command-line Auto Loading or create cards before the GUI is active.

The card lives in the game's source VMC directory. Its name follows the same
group/title-ID rule as the VMC screen, with `_0` for slot 1, so known multidisc
groups share a card. An existing supported-size card under that name is reused.
Neutrino also receives an existing odd-size card as is, following its own card
handling; native OPL requires a supported size. This option never resizes or
reformats an existing file. Assigned cards and disabled
slots remain unchanged. Slot 2 is untouched.

Apps and PS1 rows are skipped. HTTP has no writable VMC backend, and internal
APA HDD games under Neutrino have no supported VMC path, so those are skipped
too. Favorites resolve the owning source before applying this policy.
UDPFS and UDPBD use Neutrino regardless of the saved loader preference; SMB uses
the native core. The same effective-loader rules govern VMC checks and warnings.

Creation shows progress and accepts the configured Cancel button. Cancellation
keeps the menu open and does not assign the card. The formatter removes its
cancelled partial image before reporting completion. A card that completed
before cancellation remains intact but is not assigned by that cancelled launch.
Working jobs have no automatic two-minute deadline: slow devices may legitimately
take longer. After Cancel, the menu waits up to 600 more status polls for cleanup.
If cleanup cannot be confirmed, it stays in the menu without assigning the card.
A blocked device RPC can still delay a poll; this is not a hard wall-clock timeout.
The formatter releases its abort semaphore before cluster seek/write, so the
abort/status request path can remain responsive while device IO is stalled.
Subsequent automatic launches refuse while the formatter still reports a job,
so a preallocated but unfinished image cannot be mistaken for a reusable card.

Unreadable images and images with an unsupported native size are preserved and
are not automatically assigned by that path. Failed creation submission or a reported formatting failure displays
an error and allows the game to launch without a newly assigned VMC. A settings
write failure is reported separately; the successfully created card is retained
and its assignment remains available to the current launch.
After successful creation, the source is probed again for an existing 8 MB image
before assignment. Favorites re-resolve their source after modal progress;
changed rows, source instances, device state or source modes refuse continuation.

The menu owns its launch configuration across progress screens, then checks
that the selected row still has the same identity before handoff. A source
refresh cannot free that configuration or silently redirect the launch to a
different row. These safeguards and formatter scheduling/failure behavior have
host regression coverage. Physical-console creation, cancellation, device
removal and filesystem behavior still require acceptance testing.

## Known failed-format retry limitation

Size is not proof of a fully formatted card. A formatter failure after erasing
the complete image can leave an 8 MB file without its final metadata. On a later
launch, the current size-only probe can reuse that file. This affects both the
original project and this C++ migration; see
[original issue #941](https://github.com/NathanNeurotic/Open-PS2-Loader/issues/941)
and [migration issue #20](https://github.com/NathanNeurotic/RiptOPL/issues/20).
The changes above do not establish structural or interruption-safe validation.
Preserve existing saves while addressing failed-output ownership and recovery;
unconditionally deleting files for every formatter error is unsafe.
