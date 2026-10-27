#ifndef __ACHIEVEMENTS_H
#define __ACHIEVEMENTS_H

// The RA achievement browser (src/sources/achievements.cpp): Caduceus account pages, or the
// xeRAbora PC's library. Requests run on the I/O thread; the GUI reads a snapshot.
constexpr int ACH_PAGE_SIZE = 3;
enum {
    ACH_IDLE,
    ACH_LOADING,
    ACH_READY,
    ACH_OFFLINE,
    ACH_ERROR,
    ACH_UNSUPPORTED,
    ACH_NOT_PLAYED // Xerabora: known to RetroAchievements, not yet in the account library
};

typedef struct
{
    int id, total, earned, hardcore, points;
    char icon[33], title[57], description[101], date[20];
} achievement_entry_t;

typedef struct
{
    int state, page, total, gameId, earned, maximum, count;
    char kind, user[25], title[57];
    achievement_entry_t entries[ACH_PAGE_SIZE];
} achievement_page_t;

int achievementsBusy(void);
// kind 'G' (library) or 'A' (one game's set, target its ID); filter 0 All, 1 Earned, 2 Locked, 3 Hardcore.
int achievementsRequest(char kind, int page, int filter, const char *target);
// One ISO image's set, found by its hash.
int achievementsRequestImage(const char *path, const char *startup);
void achievementsSnapshot(achievement_page_t *result);
// A Caduceus CADB1 page body.
int achievementsParse(char *reply, achievement_page_t *result);
/* Xerabora: parse an xeRAbora /library ('G') or /game ('A') document into the cached list, serve
   one filtered page of it, and mark it stale so the next request refetches (Select). */
int achievementsParseXerabora(char kind, const char *json, int length);
void achievementsXeraboraPage(achievement_page_t *out, char kind, int page, int filter);
void achievementsForget(void);

#endif
