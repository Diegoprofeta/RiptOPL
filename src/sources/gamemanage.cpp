/*
  gamemanage.cpp -- Hide Game and Delete everything.

  Ported from RIPPS2 by Akilluminati47 (akilluminati47/RIPPS2, build 114: SHROUD and LAST RITES).

  Hide Game: a hidden game leaves every list (its device's page, All Games, Favourites, Recent,
  Random Game) until it is shown again. Each device keeps its own list, hidden.txt in its prefix
  beside CFG/ and ART/, so the list goes where the drive goes. One line a game: "0" (PS2) or "1"
  (PS1), a tab, then the game's name. Settings > Show hidden games lists them anyway, so they can be
  shown again from the game's menu.

  Delete everything: the game's parts through the source's own delete (which also rebuilds ul.cfg),
  then its CFG, art and cheats, unless another copy of the game on the same page uses them. VMC
  saves are kept. The APA HDD has no delete here: removing a partition is not taken.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>

#include "include/opl.h" // umbrella: SDK base types (u32/GSTEXTURE) that iosupport.h depends on
#include "include/gamemanage.h"
#include "include/gamesource.h"
#include "include/supportbase.h"
#include "include/sema_lock.h"

int gShowHidden;

typedef struct
{
    char prefix[160]; // the prefix the list was read from; another prefix reads it again
    int loaded, count;
    char *names[HIDDEN_MAX];
    unsigned char ps1[HIDDEN_MAX];
} hidden_list_t;

static hidden_list_t hiddenLists[MODE_COUNT];
static int hiddenSema = -1;

void hiddenInit(void)
{
    if (hiddenSema < 0) {
        ee_sema_t sema;
        sema.init_count = 1;
        sema.max_count = 1;
        sema.option = 0;
        sema.attr = 0;
        hiddenSema = CreateSema(&sema);
    }
}

// The prefix a source keeps its list in; NULL when it keeps none (the network catalogue, apps).
static const char *hiddenPrefix(item_list_t *source, char *out, int size)
{
    int mode = source->mode;
    if (mode < 0 || mode >= MODE_COUNT || mode == HTTP_MODE || mode == APP_MODE || mode == FAV_MODE || source->source == NULL ||
        !gsOf(source)->hasPrefix())
        return NULL;
    const char *prefix = gsOf(source)->prefix(source);
    if (prefix == NULL || prefix[0] == '\0' || (int)strlen(prefix) >= size)
        return NULL;
    snprintf(out, size, "%s", prefix);
    return out;
}

static void hiddenClear(hidden_list_t *list)
{
    for (int i = 0; i < list->count; i++)
        free(list->names[i]);
    list->count = 0;
}

static int hiddenAppend(hidden_list_t *list, int ps1, const char *name)
{
    if (list->count >= HIDDEN_MAX || name[0] == '\0')
        return 0;
    char *copy = static_cast<char *>(malloc(strlen(name) + 1));
    if (copy == NULL)
        return 0;
    strcpy(copy, name);
    list->ps1[list->count] = ps1 != 0;
    list->names[list->count++] = copy;
    return 1;
}

// (with the lock held)
static hidden_list_t *hiddenLoad(item_list_t *source, int force)
{
    char prefix[160], path[200], line[HIDDEN_NAME_MAX + 8];
    hidden_list_t *list = &hiddenLists[source->mode];

    if (hiddenPrefix(source, prefix, sizeof(prefix)) == NULL) {
        hiddenClear(list);
        list->loaded = 0;
        return NULL;
    }
    if (list->loaded && !force && !strcmp(list->prefix, prefix))
        return list;
    hiddenClear(list);
    snprintf(list->prefix, sizeof(list->prefix), "%s", prefix);
    list->loaded = 1;
    snprintf(path, sizeof(path), "%s%s", prefix, HIDDEN_FILE);
    FILE *f = fopen(path, "r");
    if (f == NULL)
        return list;
    while (fgets(line, sizeof(line), f) != NULL) {
        char *end = line + strlen(line);
        while (end > line && (end[-1] == '\n' || end[-1] == '\r'))
            *--end = '\0';
        // "0<tab>name" or "1<tab>name"; a bare name is a PS2 game, '#' starts a comment
        if (line[0] == '\0' || line[0] == '#')
            continue;
        if ((line[0] == '0' || line[0] == '1') && line[1] == '\t')
            hiddenAppend(list, line[0] == '1', line + 2);
        else
            hiddenAppend(list, 0, line);
    }
    fclose(f);
    return list;
}

static int hiddenFind(const hidden_list_t *list, int ps1, const char *name)
{
    for (int i = 0; i < list->count; i++)
        if (list->ps1[i] == (ps1 != 0) && !strcmp(list->names[i], name))
            return i;
    return -1;
}

static bool hiddenValid(const item_list_t *source)
{
    return source != NULL && source->mode >= 0 && source->mode < MODE_COUNT;
}

void hiddenReload(item_list_t *source)
{
    if (!hiddenValid(source))
        return;
    raii::SemaLock lock(hiddenSema);
    hiddenLoad(source, 1);
}

int hiddenHas(item_list_t *source, int ps1, const char *name)
{
    if (!hiddenValid(source) || name == NULL || name[0] == '\0')
        return 0;
    raii::SemaLock lock(hiddenSema);
    hidden_list_t *list = hiddenLoad(source, 0);
    return list != NULL && hiddenFind(list, ps1, name) >= 0;
}

static int hiddenSave(const hidden_list_t *list)
{
    char path[200];
    snprintf(path, sizeof(path), "%s%s", list->prefix, HIDDEN_FILE);
    if (list->count == 0) {
        int fd = open(path, O_RDONLY);
        if (fd < 0)
            return 1;
        close(fd);
        return unlink(path) == 0;
    }
    FILE *f = fopen(path, "w");
    if (f == NULL)
        return 0;
    int ok = 1;
    for (int i = 0; i < list->count && ok; i++)
        ok = fprintf(f, "%d\t%s\n", list->ps1[i], list->names[i]) > 0;
    return (fclose(f) == 0) && ok;
}

int hiddenSet(item_list_t *source, int ps1, const char *name, int hide)
{
    char copy[HIDDEN_NAME_MAX];
    int result;

    if (!hiddenValid(source) || name == NULL || name[0] == '\0')
        return -1;
    snprintf(copy, sizeof(copy), "%s", name); // name may be a row of the page the refresh rebuilds
    raii::SemaLock lock(hiddenSema);
    hidden_list_t *list = hiddenLoad(source, 1);
    if (list == NULL) {
        result = -1;
    } else {
        int at = hiddenFind(list, ps1, copy);
        if (hide ? at >= 0 : at < 0) {
            result = 1; // already as asked
        } else if (hide) {
            result = hiddenAppend(list, ps1, copy) && hiddenSave(list);
            if (!result && hiddenFind(list, ps1, copy) >= 0) {
                free(list->names[--list->count]); // not saved: not hidden
            }
        } else {
            char *gone = list->names[at];
            unsigned char gonePs1 = list->ps1[at];
            for (int i = at; i + 1 < list->count; i++) {
                list->names[i] = list->names[i + 1];
                list->ps1[i] = list->ps1[i + 1];
            }
            list->count--;
            result = hiddenSave(list);
            if (result) {
                free(gone);
            } else { // not saved: still hidden
                for (int i = list->count; i > at; i--) {
                    list->names[i] = list->names[i - 1];
                    list->ps1[i] = list->ps1[i - 1];
                }
                list->names[at] = gone;
                list->ps1[at] = gonePs1;
                list->count++;
            }
        }
    }
    return result;
}

// ---- Delete everything ----

static void gmAdd(gm_delete_plan_t *plan, int what, const char *dir, char sep, const char *name)
{
    if (plan->count >= GM_MAX_FILES)
        return;
    if (snprintf(plan->files[plan->count].path, sizeof(plan->files[0].path), "%s%c%s", dir, sep, name) >=
        (int)sizeof(plan->files[0].path))
        return;
    plan->files[plan->count++].what = what;
    if (what == GM_FILE_CFG)
        plan->cfg++;
    else if (what == GM_FILE_ART)
        plan->art++;
    else
        plan->cht++;
}

static int gmIsArt(const char *name, const char *startup)
{
    static const char *const exts[] = {".png", ".jpg", ".jpeg"};
    size_t n = strlen(startup), len = strlen(name);
    if (len <= n + 1 || strncasecmp(name, startup, n) != 0 || name[n] != '_')
        return 0;
    for (unsigned int i = 0; i < sizeof(exts) / sizeof(exts[0]); i++) {
        size_t e = strlen(exts[i]);
        if (len > n + 1 + e && !strcasecmp(name + len - e, exts[i]))
            return 1;
    }
    return 0;
}

// Any letter case, as the art index and the cheat loader find them. A folder that cannot be listed
// falls back to the names OPL itself looks for.
static void gmCollect(gm_delete_plan_t *plan, const char *dir, char sep, const char *startup, int what)
{
    char want[160];
    DIR *d = opendir(dir);
    if (d == NULL) {
        const char *colon = strchr(dir, ':');
        char alt[200];
        if (colon != NULL && colon[1] != '\0' && colon[1] != '/' && colon[1] != '\\' &&
            snprintf(alt, sizeof(alt), "%.*s/%s", (int)(colon - dir) + 1, dir, colon + 1) < (int)sizeof(alt))
            d = opendir(alt); // "mass0:ART" is listed as "mass0:/ART" (see artindex.cpp)
    }
    if (what != GM_FILE_ART)
        snprintf(want, sizeof(want), "%s.%s", startup, what == GM_FILE_CFG ? "cfg" : "cht");
    if (d != NULL) {
        struct dirent *e;
        while ((e = readdir(d)) != NULL) {
            if (what == GM_FILE_ART ? gmIsArt(e->d_name, startup) : !strcasecmp(e->d_name, want))
                gmAdd(plan, what, dir, sep, e->d_name);
        }
        closedir(d);
        return;
    }

    static const char *const art[] = {"COV", "COV2", "ICO", "LAB", "LGO", "BG", "SCR", "SCR2", "BG_00", "SCR_00", "SCR_01"};
    static const char *const artExt[] = {"png", "jpg", "jpeg"};
    char path[256];
    if (what != GM_FILE_ART) {
        const char *const ext[] = {what == GM_FILE_CFG ? "cfg" : "cht", what == GM_FILE_CFG ? NULL : "CHT"};
        for (int k = 0; k < 2 && ext[k] != NULL; k++) {
            snprintf(want, sizeof(want), "%s.%s", startup, ext[k]);
            snprintf(path, sizeof(path), "%s%c%s", dir, sep, want);
            int fd = open(path, O_RDONLY);
            if (fd >= 0) {
                close(fd);
                gmAdd(plan, what, dir, sep, want);
            }
        }
        return;
    }
    for (unsigned int i = 0; i < sizeof(art) / sizeof(art[0]); i++)
        for (unsigned int k = 0; k < sizeof(artExt) / sizeof(artExt[0]); k++) {
            snprintf(want, sizeof(want), "%s_%s.%s", startup, art[i], artExt[k]);
            snprintf(path, sizeof(path), "%s%c%s", dir, sep, want);
            int fd = open(path, O_RDONLY);
            if (fd >= 0) {
                close(fd);
                gmAdd(plan, what, dir, sep, want);
            }
        }
}

int gmPlanDelete(item_list_t *support, int id, gm_delete_plan_t *plan)
{
    static const char *const dirs[] = {"CFG", "ART", "CHT"};
    char dir[200];

    memset(plan, 0, sizeof(*plan));
    if (support == NULL || support->source == NULL || support->mode == HDD_MODE || support->mode == FAV_MODE)
        return 0;
    GameSource *gs = gsOf(support);
    if (!gs->hasDelete() || !gs->hasGame() || !gs->hasPrefix())
        return 0;
    base_game_info_t *game = static_cast<base_game_info_t *>(gs->game(support, id));
    const char *prefix = gs->prefix(support);
    if (game == NULL || game->format == GAME_FORMAT_FOLDER || game->startup[0] == '\0' || game->parts <= 0 ||
        prefix == NULL || prefix[0] == '\0')
        return 0;
    plan->parts = game->parts;

    int count = gs->count(support);
    for (int i = 0; i < count && !plan->shared; i++) {
        const char *startup = i != id ? gs->startup(support, i) : NULL;
        plan->shared = startup != NULL && !strcmp(startup, game->startup);
    }
    if (plan->shared)
        return 1; // another copy keeps the CFG, art and cheats

    char sep = support->mode == ETH_MODE ? '\\' : '/';
    for (int what = GM_FILE_CFG; what <= GM_FILE_CHT; what++) {
        snprintf(dir, sizeof(dir), "%s%s", prefix, dirs[what]);
        gmCollect(plan, dir, sep, game->startup, what);
    }
    return 1;
}

int gmDeleteExtras(const gm_delete_plan_t *plan)
{
    int failed = 0;
    for (int i = 0; i < plan->count; i++)
        failed += unlink(plan->files[i].path) != 0;
    return failed;
}
