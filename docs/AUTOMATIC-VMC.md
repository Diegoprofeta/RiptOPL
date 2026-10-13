# Automatic VMC creation

In **Settings → Game Launching**, enable **Create VMC on First Launch** to create
and assign an 8 MB card when a PS2 game's slot 1 has no card assigned. The option
defaults off and is saved as `auto_create_vmc`. It applies to menu launches,
including PS2 Favorites, on all three ps2build editions. It does not change
command-line Auto Loading or create cards before the GUI is active.

The card lives in the game's source VMC directory. Its name follows the same
group/title-ID rule as the VMC screen, with `_0` for slot 1, so known multidisc
groups share a card. An existing supported-size card under that name is reused;
it is never resized or reformatted by this option. Assigned cards and disabled
slots remain unchanged. Slot 2 is untouched.

Apps and PS1 rows are skipped. HTTP has no writable VMC backend, and internal
APA HDD games under Neutrino have no supported VMC path, so those are skipped
too. Favorites resolve the owning source before applying this policy.

Creation shows progress and accepts the configured Cancel button. Cancellation
keeps the menu open and does not assign the card. The formatter removes its
cancelled partial image before reporting completion. A card that completed
before cancellation remains intact but is not assigned by that cancelled launch.
Status polling has a 7,200-frame limit; if completion cannot be confirmed, the
launch is cancelled and no card is assigned. A blocked device RPC can still
delay a poll; this is not a hard wall-clock timeout.
Subsequent automatic launches refuse while the formatter still reports a job,
so a preallocated but unfinished image cannot be mistaken for a reusable card.

An unreadable or malformed existing image is preserved and is not automatically
assigned. Failed creation submission or a reported formatting failure displays
an error and allows the game to launch without a newly assigned VMC. A settings
write failure is reported separately; the successfully created card is retained
and its assignment remains available to the current launch.

The menu owns its launch configuration across progress screens, then checks
that the selected row still has the same identity before handoff. A source
refresh cannot free that configuration or silently redirect the launch to a
different row. These safeguards and formatter scheduling/failure behavior have
host regression coverage. Physical-console creation, cancellation, device
removal and filesystem behavior still require acceptance testing.
