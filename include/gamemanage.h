#ifndef __GAMEMANAGE_H
#define __GAMEMANAGE_H

// Hide Game and Delete everything, ported from RIPPS2 (akilluminati47/RIPPS2, build 114).

#include "include/iosupport.h"

constexpr const char *HIDDEN_FILE = "hidden.txt"; // in the source's prefix, beside CFG/ and ART/
constexpr int HIDDEN_MAX = 512;                   // games one device's list keeps
constexpr int HIDDEN_NAME_MAX = 256;

extern int gShowHidden; // Settings: list hidden games anyway, so they can be shown again

void hiddenInit(void);
// The source's list was read again (I/O thread): read its hidden list again too. source is the
// real list (a module's support), never a proxy copy.
void hiddenReload(item_list_t *source);
// 1 when the source's hidden list names this game. Loads the list once.
int hiddenHas(item_list_t *source, int ps1, const char *name);
// Adds (hide = 1) or removes a game. 1 saved, 0 the list could not be written, -1 the source keeps
// no list. The caller rebuilds the pages (menusys.cpp hiddenRefresh).
int hiddenSet(item_list_t *source, int ps1, const char *name, int hide);

// Row helpers, defined in src/ui/menusys.cpp beside the menus that use them.
// 1 when this row of a page (device page or Favourites/All Games) is a hidden game.
int hiddenRow(item_list_t *support, int id);

// Delete everything: the game's parts, and its CFG, art and cheats unless another copy of the game
// on the same page uses them. VMC saves are kept.
enum { GM_FILE_CFG = 0,
       GM_FILE_ART,
       GM_FILE_CHT };
constexpr int GM_MAX_FILES = 64;
typedef struct
{
    int parts, cfg, art, cht, shared, count;
    struct
    {
        char path[256];
        int what;
    } files[GM_MAX_FILES];
} gm_delete_plan_t;

// Fills plan for a PS2 game row of a device page. 0 when the row is not a game this can delete.
int gmPlanDelete(item_list_t *support, int id, gm_delete_plan_t *plan);
// Removes the planned extras; returns how many could not be removed.
int gmDeleteExtras(const gm_delete_plan_t *plan);

#endif
