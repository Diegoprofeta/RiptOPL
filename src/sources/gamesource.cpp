// GameSource: the base class of the game sources; defaults for the optional methods. See gamesource.h.

#include "include/opl.h"
#include "include/gamesource.h"
#include "include/cuesupport.h" // cueIsCueEntry
#include "include/vcdsupport.h" // PS1_ROW_* + the PS1-row id memo

GameSource::GameSource(short int mode_, char appsPriority_, unsigned char flags_, int delay_, int updateDelay_, unsigned caps)
{
    mode = mode_;
    appsPriority = appsPriority_;
    enabled = 0;
    flags = flags_;
    delay = delay_;
    updateDelay = updateDelay_;
    priv = NULL;
    owner = NULL;
    viewOverride = 0;
    source = this;
    caps_ = caps;
}

char *GameSource::prefix(item_list_t *) { return NULL; }
void GameSource::deleteGame(item_list_t *, int) {}
void *GameSource::game(item_list_t *, int) { return NULL; }
int GameSource::checkVmc(item_list_t *, char *, int) { return -1; }
int GameSource::createVmc(item_list_t *itemList, char *name, int createSize, int) { return checkVmc(itemList, name, createSize); }
void GameSource::launchVcd(item_list_t *, const char *, config_set_t *) {}
int GameSource::artArchivePath(item_list_t *, char *, int) { return 0; }
void GameSource::launchCue(item_list_t *, const char *, config_set_t *) {}
int GameSource::rowView(item_list_t *, int) { return 0; }
int GameSource::sourceId(item_list_t *, int id) { return id; }
int GameSource::saveCueSettings(item_list_t *, int, const char *, config_set_t *) { return 0; }

int GameSource::ps1ArtId(item_list_t *itemList, int id, const char *startup, char *out, int outSize)
{
    // Favourites match the art value against fav identities (favGetArtMode); keep them name-keyed.
    if (itemList->mode == FAV_MODE || itemList->mode == APP_MODE || !hasGame())
        return 0;
    const base_game_info_t *row = (const base_game_info_t *)game(itemList, id);
    if (row == NULL)
        return 0;
    int kind = PS1_ROW_VCD;
    if (cueIsCueEntry(row))
        kind = PS1_ROW_CUE;
    else if (strcasecmp(row->extension, ".VCD") != 0)
        return 0;
    ps1RowIdRequest(startup, kind); // verify provisional filename ids too
    return ps1RowIdCached(startup, kind, out, outSize);
}
