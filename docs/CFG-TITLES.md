# CFG titles in game lists

Enable **Show CFG Titles in Game Lists** in Interface settings to display each
game's `Title` from its per-game CFG. It is off by default. Save the setting to
retain it across restarts (`cfg_titles_in_lists=1` in `settings_riptopl.cfg`).

The setting changes list text, alphabetical sorting and the selected game's
title. It preserves the source filename, game ID, startup caption and launch
arguments. Missing, empty or invalid titles fall back to the existing name.
Apps, app Favorites and folder rows retain their names. Game Favorites resolve
the owning source's configuration; RetroAchievements badge prefixes remain.

Titles must be valid UTF-8 without control characters. Leading/trailing spaces
and tabs are trimmed. Long titles are shortened at a character boundary to fit
the 128-byte title buffer. Glyph display depends on the selected font.

Enabling this setting reads a CFG for each game when refreshing a list. Large
or network libraries can take longer to refresh. Reads run on the IO worker;
rendering and sorting use an owned cache and perform no configuration IO.
Changing the setting queues fresh device, HTTP and Favorites lists even when
automatic refresh is disabled. Turning it off restores names immediately.

This adapts original Open-PS2-Loader PR #932 at
`dea980ef4549de41dd1ee5e1261238a22da2080b` to the C++ GameSource API. It does
**not** implement the original repository's separate optional `font_CJK.ttf`
fallback from #917. That font feature remains migration work; UTF-8 parsing
alone cannot supply missing glyphs.

Host regressions execute the actual standard/RA cache, allocation failures,
UTF-8 cleanup, list sorting and settings refresh order. PS2 native builds, CI
packages and physical-console acceptance are separate validation boundaries.
