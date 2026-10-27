/*
  RA: the badge in the game list that marks a checked, tracked game.

  After a check the console stores the watch list next to the game as
  `<device>RA/<serial>.wl`. That file's presence is the whole record of
  RA support; there is no separate registry to drift out of sync.

  We look in the same places and in the same order as the loader does
  before launch (`sbLoadWatchList`): the game's own device first, then
  the share. Otherwise the badge would lie, showing what the launch
  cannot find or hiding lists prepared on the PC.

  Recomputed whenever the game list is refreshed, which happens on the
  I/O thread where file operations are safe. It must not be called from
  the menu handler, for the same reason mounting must not.

  Upstream design and implementation: hacan359. Port note: upstream keys
  the slot table on RA_BADGE_SLOTS=4 ("OPL has exactly this many devices"),
  which is not true of this fork -- MODE_COUNT is 14 (eight BDM slots, ETH,
  HDD, APP, MMCE, FAV, UDPFS). With four slots the badge cache silently
  mis-attributes lists across devices.

  This file compiles to nothing unless RETROACHIEVEMENTS=1.
*/

#ifdef RETROACHIEVEMENTS

#include "include/opl.h"
#include "include/util.h"
#include "include/supportbase.h"
#include "include/rabadge.h"
#include "include/gamesource.h"
#include "include/rahash.h"
#include "include/bdmsupport.h"
#include "include/favsupport.h"
#include "include/host.h"
#include "include/libview.h" // LIB_VIEW_PS1
#include "include/vcdsupport.h"

#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>

#define RA_BADGE      "RA "   /* prefix before the name; ASCII only, the stock \
                                 theme font has no other glyphs */
#define RA_SUFFIX     " [RA]" /* the same mark after the name (gRABadgeSuffix) */
#define RA_BADGE_TEXT (ISO_GAME_NAME_MAX + 8)

RaBadge gRaBadge;

void raBadgeRefresh(item_list_t *support, int count)
{
    gRaBadge.refresh(support, count);
}

const char *raBadgeText(item_list_t *support, int idx)
{
    return gRaBadge.text(support, idx);
}

struct ra_badge_slot *RaBadge::slotFor(item_list_t *support)
{
    int i;

    for (i = 0; i < MODE_COUNT; i++)
        if (slots_[i].support == support)
            return &slots_[i];

    for (i = 0; i < MODE_COUNT; i++) {
        if (slots_[i].support == NULL) {
            slots_[i].support = support;
            return &slots_[i];
        }
    }

    return NULL;
}

/* The prefix a row's watch list lives under: a favourite's is its source device's. */
const char *RaBadge::rowPrefix(item_list_t *support, int idx)
{
    item_list_t view;
    item_list_t *owner = support->mode == FAV_MODE ? gFavSupport.ownerView(idx, &view) : support;

    return owner != NULL && gsOf(owner)->hasPrefix() ? gsOf(owner)->prefix(owner) : NULL;
}

/* A PS1 VCD keeps its filename for artwork and settings, but its watch list (and POPStarter
   telemetry) is keyed by the full VCD path, since many images share a boot name. Resolved here,
   on the refresh worker, without reading the image. 1: a USB VCD, out holds its key; 0: not a
   PS1 row; -1: a PS1 row POPStarter cannot track (Ember, or not on USB). */
int RaBadge::vcdKey(item_list_t *support, int idx, const char *prefix, char *out, int outSize)
{
    char path[256];
    const char *colon, *name;
    int isVcd, sourceMode;

    if (host::library().listRowView(support, idx) != LIB_VIEW_PS1)
        return 0;
    if (support->mode == FAV_MODE) {
        isVcd = favGetItemKind(idx) == FAV_KIND_VCD;
        sourceMode = favGetItemSourceMode(idx);
    } else {
        const base_game_info_t *game = gsOf(support)->hasGame() ? static_cast<const base_game_info_t *>(gsOf(support)->game(support, idx)) : NULL;
        isVcd = game != NULL && !strcasecmp(game->extension, ".VCD");
        sourceMode = support->mode;
    }
    if (!isVcd || !bdmModeIsUSB(sourceMode) || prefix == NULL || (colon = strchr(prefix, ':')) == NULL)
        return -1;
    name = gsOf(support)->name(support, idx);
    if (name == NULL || !name[0] ||
        snprintf(path, sizeof(path), "%.*s/POPS/%s.VCD", (int)(colon - prefix) + 1, prefix, name) >= (int)sizeof(path))
        return -1;
    return raVcdWatchKey(path, out, outSize) == 0 ? 1 : -1;
}

int RaBadge::watchListExists(const char *prefix, const char *serial, int localOnly)
{
    char path[256];
    struct stat st;

    if (prefix == NULL || serial == NULL || serial[0] == '\0')
        return 0;

    snprintf(path, sizeof(path), "%sRA/%s.wl", prefix, serial);
    if (stat(path, &st) == 0 && st.st_size > 0)
        return 1;

    /* The same fallback the loader uses: lists prepared on the PC live
       on the share. */
    if (!localOnly && strncmp(prefix, "smb0:", 5) != 0) {
        snprintf(path, sizeof(path), "smb0:RA/%s.wl", serial);
        if (stat(path, &st) == 0 && st.st_size > 0)
            return 1;
    }

    return 0;
}

void RaBadge::refresh(item_list_t *support, int count)
{
    struct ra_badge_slot *slot;
    const char *prefix;
    int i;

    if (support == NULL || (support->mode != FAV_MODE && !gsOf(support)->hasPrefix()))
        return;

    slot = slotFor(support);
    if (slot == NULL)
        return;

    if (slot->text != NULL) {
        free(slot->text);
        slot->text = NULL;
    }
    slot->count = 0;

    /* Switched off: return AFTER the clear above, never before it, so turning badges off
       drops the cache on the next list rebuild instead of freezing the last one on screen.
       text() reads this slot, and the cover mark rides on the same answer. */
    if (!gRATelemetry || !gRABadges)
        return;

    if (count <= 0)
        return;

    prefix = support->mode == FAV_MODE ? NULL : gsOf(support)->prefix(support);
    if (support->mode != FAV_MODE && prefix == NULL)
        return;

    slot->text = static_cast<char *>(malloc((size_t)count * RA_BADGE_TEXT));
    if (slot->text == NULL)
        return;

    slot->count = count;

    for (i = 0; i < count; i++) {
        char *dst = slot->text + (size_t)i * RA_BADGE_TEXT;
        const char *serial = gsOf(support)->startup(support, i);
        const char *where = support->mode == FAV_MODE ? rowPrefix(support, i) : prefix;
        char ps1Key[16];
        int ps1 = vcdKey(support, i, where, ps1Key, sizeof(ps1Key));

        if (ps1 != 0)
            serial = ps1 > 0 ? ps1Key : NULL;
        /* POPStarter's reader loads the list only from the game's device: never probe the share
           for a VCD, which is slow and could mark a list the launch cannot use. */
        if (watchListExists(where, serial, ps1 > 0)) {
            // Placement changes only this display text; row identity and sorting stay clean.
            const char *name = vcdDisplayNameForRow(support, i, gsOf(support)->name(support, i));
            if (gRABadgeSuffix)
                snprintf(dst, RA_BADGE_TEXT, "%s%s", name, RA_SUFFIX);
            else
                snprintf(dst, RA_BADGE_TEXT, "%s%s", RA_BADGE, name);
        } else
            dst[0] = '\0'; /* empty means show the plain name */
    }
}

const char *RaBadge::text(item_list_t *support, int idx)
{
    struct ra_badge_slot *slot = NULL;
    char *text;
    int i;

    for (i = 0; i < MODE_COUNT; i++)
        if (slots_[i].support == support)
            slot = &slots_[i];

    if (slot == NULL || slot->text == NULL || idx < 0 || idx >= slot->count)
        return NULL;

    text = slot->text + (size_t)idx * RA_BADGE_TEXT;

    return text[0] ? text : NULL;
}

#endif /* RETROACHIEVEMENTS */
