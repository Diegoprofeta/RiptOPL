#ifndef CFGTITLE_H
#define CFGTITLE_H

#include <tamtypes.h>
#include "include/iosupport.h"

constexpr int CFG_TITLE_MAX = 128;

// Per-source presentation cache. Source/launch/CFG/art/Favorites identity stays unchanged.
// Refresh/forget belong to the IO worker; GUI readers borrow titles within the frame lock.
class CfgTitles
{
public:
    static int clean(const char *in, char *out, int size);
    void refresh(item_list_t *support, int count);
    void forget(item_list_t *support);
    const char *forRow(item_list_t *support, int id);
    const char *displayName(item_list_t *support, int id, const char *text);

private:
    struct Slot
    {
        item_list_t *support;
        int count;
        char **title;
    };
    Slot slots_[MODE_COUNT] = {};
    Slot *findSlot(item_list_t *support);
    Slot *claimSlot(item_list_t *support);
    static void swapTable(Slot *slot, char **fresh, int count);
};

extern CfgTitles gCfgTitles;
int cfgTitleClean(const char *in, char *out, int size);
void cfgTitleRefresh(item_list_t *support, int count);
void cfgTitleForget(item_list_t *support);
const char *cfgTitleForRow(item_list_t *support, int id);
const char *cfgTitleDisplayName(item_list_t *support, int id, const char *text);

#endif
