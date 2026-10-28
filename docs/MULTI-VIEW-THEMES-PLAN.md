# Multi-view themes: plan

Status: in progress on branch `claude/project-thread-skxuai`. Nothing here is hardware-tested.
Design idea: KrahJohlito (one theme cfg defines several views; views share elements and override only
what they declare; a button or setting switches views).

## Goal

One `conf_theme.cfg` can describe several **views** of the main and info pages: List, Coverflow,
PSBBN Flow and Grid. A view inherits every block it does not declare. The user picks the view with a
setting, and holding L3 cycles views. Themes that declare a single view keep working unchanged.

The unified All Games list is a separate, OPL-side feature. It decides which rows a page shows; a view
decides how rows are drawn. Neither touches the other's configuration.

## How themes work before this change

- `<Coverflow>` and `<PSBBN Flow>` are separate built-in themes, each with its own embedded cfg
  (`misc/theme_coverflow.cfg`, `misc/theme_psbbn_flow.cfg`). The List look is `misc/conf_theme_OPL.cfg`.
  Coverflow differs from List only in the presenter block (`Coverflow` instead of `ItemCover`); the menu
  icons, items list and the whole info page are identical.
- `main2:` in a cfg is a section prefix: the parser stores `main2_type`, `main2_y` and so on.
- Elements are parsed into families (main/info for games, apps, favs, vcd and the opt-in favsVcd/favsApps).
  A family inherits **by block index**: `appsMain<j>` if present, else `main<j>`.
- Textures and cover caches are shared between families by `findDuplicate`.
- There are four global `ItemsList` slots (games, apps, favs, vcd), claimed in parse order.

## Config syntax

```
views=list,coverflow
default_view=list

# base = List view
main2:
	type=StaticImage
	default=ip
# Coverflow replaces block 2
coverflow.main2:
	type=Coverflow
	default=cover
# kinds still work inside a view
coverflow.appsMain2:
	type=Coverflow
	default=coverapp
# switch a base block off in this view
coverflow.main16_enabled=0
# a view may add blocks past the base count
coverflow.main20:
	type=StaticText
	value=Hello
```

View names: `list`, `coverflow`, `psbbn`, `grid`. Unprefixed blocks are the base. The base should be the
List view so stock OPL and other forks, which ignore the prefixed keys, still load the theme as a list.

### Resolution order

For block `j` in view `V` and family kind `K` (for example `apps`), the first block present wins:

1. `V.KMain<j>` (for example `coverflow.appsMain2`)
2. `V.main<j>`
3. today's chain for `K` (for example `appsMain<j>`, and for vcd `vcdMain<j>` then `appsMain<j>`)
4. `main<j>`

`info<j>` resolves the same way. A view block replaces the whole base block (block-level, like
`appsMain` today); it never merges single keys from the base block, so a view that changes `type` gets
no stale keys.

`V.main<j>_enabled=0` (or any `V.<family><j>_enabled=0`) removes the block in that view only.

A view can declare blocks past the end of the base list. The block count of a view is the larger of the
base count and the view's own count.

### View-scoped global keys

`V.<key>` overrides a theme-wide key in that view, for example `coverflow.coverflow_cover_offset` or
`psbbn.use_real_height`. Colour keys follow today's rules (built-in themes carry none, see #574).

### Declared views

- `views=` lists the views the theme supports, in ring order. Absent: the theme supports only its
  native view (detected from its base blocks: `PSBBNFlow` = psbbn, `Coverflow` = coverflow, else list),
  plus any view it declares blocks for.
- `default_view=` is the view used when the user has not chosen one. Absent: the native view.
- `auto_views=0` stops RiptOPL from synthesising views the theme does not declare (step 5).

## Prerequisite: config key length

`CONFIG_KEY_NAME_LEN` was 32, and `favsVcdMain12_reflection_offset` is already 31 characters. A view
prefix would silently truncate keys, so the limit goes to 64 first (step 1). Key names in a config file
longer than the limit are now rejected rather than truncated, so two long keys can no longer collide.

## Switching

- A **View** setting under Display settings is the source of truth, saved per theme in
  `settings_riptopl.cfg`.
- **Hold L3** (about half a second) cycles to the next declared view; a tap on L3 stays the
  library-view ring and R3 stays favourites. The hint bar names the view.
- Phase 1 applies a view change by reloading the theme. It costs no extra EE RAM. Phase 2 keeps every
  declared view resident for an instant switch, only if the reload is too slow on real hardware.

## Auto-normalised views (later step)

For a view the theme does not declare, RiptOPL keeps the theme's background, colours, fonts, menu icons,
hints and info page, and swaps only the presenter, using per-view rules by element type:

- Coverflow: hide `ItemCover` in main, add a `Coverflow` element from the built-in template.
- PSBBN Flow: hide `ItemCover`, add `PSBBNFlow`, move `ItemsList` to the template position.
- Grid: hide `ItemsList` and `ItemCover`, add `Grid`.
- List: hide flow elements, add `ItemsList`/`ItemCover` if the theme has none.

This ships behind a setting until it has been checked against community themes in PCSX2.

## Steps

1. Raise `CONFIG_KEY_NAME_LEN`; reject over-long keys; host test.
2. View-aware block lookup in the theme loader: `views=`, `default_view=`, prefixed blocks, append and
   disable, view-scoped globals. Active view chosen at load; switching reloads. Host test of the
   resolution order.
3. Merge the three built-in cfgs into one embedded cfg with `coverflow.` and `psbbn.` blocks. Map saved
   `<Coverflow>` / `<PSBBN Flow>` theme names to `<OPL>` plus that view.
4. View setting and hold-L3 cycling.
5. Auto-normalised views behind a setting.
6. `Grid` element (2D navigation; at most about 16 covers visible, `COVER_CACHE_SLOTS` is 20).
7. Phase 2 resident views, only if needed.
8. Theme-maker docs: `THEME_ENGINE.md`, site and wiki.
9. Port to legacy Open-PS2-Loader (`src/themes.c` has the same structure).

## Testing

Host tests for the config parser and view resolution, a ps2build build, PCSX2 screenshots of each view
for the built-in theme and a few community themes, then one hardware pass: switch views, launch a game,
return, launch a second game, change theme with a view saved, cold and warm boot.

## Open questions

- Remember the view per theme only, or per device page too (like the L3 ring)?
- Auto-normalised views on by default, or opt-in?
- Is hold-L3 reliable on testers' pads and adapters?
- Grid shape: fixed 4x3, or theme-defined rows and columns?
- Can a theme force a different view for apps or PS1 pages?
