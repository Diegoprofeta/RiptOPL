# Fresh-start defaults

These defaults describe this C++/ps2build repository when no saved master
configuration is loaded. Updating the ELF does not reset saved settings. A new
installation folder can still discover settings on another device.

| Setting | Fresh default | Where to change it |
| --- | --- | --- |
| Menu aspect ratio | 16:9; Widescreen on | Settings ? Interface |
| Menu video mode | Auto | Settings ? Interface |
| Theme | Built-in `<OPL>` | Settings ? Interface ? Theme |
| Coverflow | Optional built-in `<Coverflow>` theme | Settings ? Interface ? Theme |
| Cover and disc artwork | On | Settings ? Interface ? Artwork Settings |
| Notifications | On | Settings ? Interface |
| PS2 logo | On | Settings ? Game Launching |
| Sound effects, boot sound, background music | On; stored volume 90 | Settings ? Audio Settings |
| Remember last played | Off | Settings ? General & System |
| Automatic VMC creation | Off | Settings ? Game Launching |
| GameID barcode | Off | Settings ? Interface |

Background music still needs a playable configured/default track. An enabled
setting alone does not supply music. Storage discovery and saved configuration
can affect the active presentation after initial defaults are applied.

Select **Theme: `<Coverflow>`** under **Settings ? Interface**, apply, and save
to keep the carousel presentation. Coverflow supports both 4:3 and 16:9;
selecting it does not toggle widescreen. Use **Widescreen: Off** for a 4:3 menu.
The carousel starts with three covers, center scale 30, 200 ms animation and
side-cover dimming off. L1/R1 page moves animate only when selection changes,
including wraps; flat list themes keep their existing page behavior.

Existing `settings_riptopl.cfg` values override fresh defaults. The legacy
`conf_riptopl.cfg` can also be migrated. Inspect the active configuration location
before diagnosing a different appearance as a failed update; preserve settings
and saves instead of deleting them to force a reset.

Menu video settings do not force the same video mode in games. **Triangle + Cross**
at boot selects the explicit 480p menu-recovery override; **Triangle + Circle**
selects Auto/interlaced recovery. Use the override suitable for the connected display.

Implementation references: [settings table](../src/core/settings.cpp),
[configuration loading](../src/app/settingsio.cpp),
[initial theme](../src/gfx/themes.cpp), [theme catalog](../include/themecatalog.h),
and [carousel tuning](../src/gfx/coverflow.cpp).

The original Open-PS2-Loader repository's newer guide describes 4:3, disabled
audio and center scale 45. This branch retains 16:9, enabled audio and scale 30.
Those are explicit migration differences, tracked in
[issue #20](https://github.com/NathanNeurotic/RiptOPL/issues/20); this documentation
update does not change runtime defaults or claim complete defaults parity.
