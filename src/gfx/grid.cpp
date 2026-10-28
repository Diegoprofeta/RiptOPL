#include "include/opl.h"
#include "include/themes.h"
#include "include/themeint.h"
#include "include/gui.h"
#include "include/renderman.h"
#include "include/textures.h"
#include "include/fntsys.h"
#include "include/texcache.h"
#include "include/ioman.h"
#include "include/grid.h"

#include <stdio.h>

/* Grid: the page's covers in rows and columns with the selection framed (multi-view themes, idea by
 * KrahJohlito; docs/MULTI-VIEW-THEMES-PLAN.md step 6). Left/Right step one cover, Up/Down one row
 * (menusys.cpp). The element's x/y place the grid's centre, width/height one cover; rows, columns and
 * spacing come from the theme's first Grid block. Covers come from the COV cache like Coverflow. */

// The size a cover takes in a cell: the page element's size, or, for a cover another family draws (a
// square app or PS1 cover on a mixed page), that element's shape fitted into the cell.
static void gridCoverSize(theme_element_t *elem, theme_element_t *coverElem, int *w, int *h)
{
    *w = elem->width;
    *h = elem->height;
    if (coverElem == elem || coverElem->width <= 0 || coverElem->height <= 0)
        return;
    if (coverElem->width * elem->height > elem->width * coverElem->height)
        *h = coverElem->height * elem->width / coverElem->width; // wider than the cell
    else
        *w = coverElem->width * elem->height / coverElem->height;
}

static void drawCell(struct menu_list *menu, struct submenu_list *item, theme_element_t *elem, int x, int y, u64 color)
{
    theme_element_t *coverElem = thmGetElemForItem(menu, item, elem);
    mutable_image_t *image = (mutable_image_t *)coverElem->extended;
    if (image == NULL || isHiddenArtworkCache(image->cache))
        return;
    GSTEXTURE *texture = getGameImageTexture(image->cache, thmGetItemSource(menu, item), &item->item);
    if (texture == NULL || texture->Mem == NULL)
        texture = image->defaultTexture ? &image->defaultTexture->source : thmGetTexture(COVER_DEFAULT);
    if (texture == NULL || texture->Mem == NULL)
        return;

    // Frame insets scale from the element that owns the overlay to the size drawn here.
    int w, h;
    gridCoverSize(elem, coverElem, &w, &h);
    if (image->overlayTexture) {
        image_texture_t *ov = image->overlayTexture;
        int cw = coverElem->width > 0 ? coverElem->width : 1;
        int ch = coverElem->height > 0 ? coverElem->height : 1;
        rmDrawOverlayPixmap(&ov->source, x, y, ALIGN_CENTER, w, h, SCALING_RATIO, color,
                            texture, ov->upperLeft_x * w / cw, ov->upperLeft_y * h / ch,
                            ov->upperRight_x * w / cw, ov->upperRight_y * h / ch,
                            ov->lowerLeft_x * w / cw, ov->lowerLeft_y * h / ch,
                            ov->lowerRight_x * w / cw, ov->lowerRight_y * h / ch, 0);
        if (image->overlayTexture2)
            rmDrawPixmap(&image->overlayTexture2->source, x, y, ALIGN_CENTER, w, h, SCALING_RATIO, color, 0);
    } else {
        rmDrawPixmap(texture, x, y, ALIGN_CENTER, w, h, SCALING_RATIO, color, 0);
    }
}

static void drawFrame(int x, int y, int w, int h, u64 color)
{
    const int t = 3;
    int x0 = x - w / 2 - t - 2, y0 = y - h / 2 - t - 2, x1 = x + (w + 1) / 2 + 2, y1 = y + (h + 1) / 2 + 2;
    rmDrawRect(x0, y0, x1 - x0 + t, t, color);
    rmDrawRect(x0, y1, x1 - x0 + t, t, color);
    rmDrawRect(x0, y0, t, y1 - y0, color);
    rmDrawRect(x1, y0, t, y1 - y0, color);
}

static void drawGrid(struct menu_list *menu, struct submenu_list *item, config_set_t *config, struct theme_element *elem)
{
    (void)config;
    if (item == NULL || elem->extended == NULL || menu == NULL || menu->item == NULL || elem->width <= 0 || elem->height <= 0)
        return;

    int count = 0, index = 0;
    for (struct submenu_list *row = menu->item->submenu; row != NULL; row = row->next) {
        if (row == item)
            index = count;
        count++;
    }
    int rows = gTheme->gridRows, columns = gTheme->gridColumns, spacing = gTheme->gridSpacing;
    int first = gridTopRow(count, index, rows, columns) * columns;

    // The selected cover first, at priority, so its neighbours cannot crowd it out of the queue.
    mutable_image_t *selected = (mutable_image_t *)thmGetElemForItem(menu, item, elem)->extended;
    if (selected)
        getGameImageTextureEx(selected->cache, thmGetItemSource(menu, item), &item->item, 1);

    // Cell pitch on screen: covers draw at SCALING_RATIO, so in widescreen they are narrower.
    int cellW = rmWideScale(elem->width), stepX = cellW + spacing, stepY = elem->height + spacing;
    int x0 = elem->posX - (columns * stepX - spacing) / 2 + cellW / 2;
    int y0 = elem->posY - (rows * stepY - spacing) / 2 + elem->height / 2;

    struct submenu_list *cell = menu->item->submenu;
    for (int i = 0; i < first && cell != NULL; i++)
        cell = cell->next;
    u64 dim = GS_SETREG_RGBA(0x60, 0x60, 0x60, 0x80);
    int selX = 0, selY = 0, shown = 0;
    for (int slot = 0; slot < rows * columns && cell != NULL; slot++, cell = cell->next) {
        int x = x0 + (slot % columns) * stepX, y = y0 + (slot / columns) * stepY;
        if (cell == item) {
            selX = x;
            selY = y;
            shown = 1;
        }
        drawCell(menu, cell, elem, x, y, cell == item ? gDefaultCol : dim);
    }
    if (shown) {
        int coverW, coverH;
        gridCoverSize(elem, thmGetElemForItem(menu, item, elem), &coverW, &coverH);
        drawFrame(selX, selY, rmWideScale(coverW), coverH, gTheme->selTextColor);
    }

    // Position in the page, under the grid's lower right corner.
    char counter[32];
    snprintf(counter, sizeof(counter), "%d/%d", index + 1, count);
    int counterWidth = rmUnScaleX(fntCalcDimensions(elem->font, counter));
    fntRenderString(elem->font, x0 + (columns - 1) * stepX + cellW / 2 - counterWidth, y0 + (rows - 1) * stepY + elem->height / 2 + 6,
                    ALIGN_LEFT, counterWidth, 0, counter, gTheme->textColor);
}

void initGrid(const char *themePath, config_set_t *themeConfig, theme_t *theme, theme_element_t *elem, const char *name)
{
    // The first Grid block sets the shape for the whole theme: navigation needs one column count.
    char key[64];
    int rows = GRID_DEFAULT_ROWS, columns = GRID_DEFAULT_COLUMNS, spacing = GRID_DEFAULT_SPACING;
    if (theme->grid != NULL) {
        rows = theme->gridRows;
        columns = theme->gridColumns;
    } else {
        snprintf(key, sizeof(key), "%s_rows", name);
        configGetInt(themeConfig, key, &rows);
        snprintf(key, sizeof(key), "%s_columns", name);
        configGetInt(themeConfig, key, &columns);
        snprintf(key, sizeof(key), "%s_spacing", name);
        configGetInt(themeConfig, key, &spacing);
        gridClamp(&rows, &columns);
    }

    // Every visible cell needs its own cover slot, or the covers on screen evict each other on every
    // frame. A theme's <name>_count may ask for more slots, never for fewer than the grid shows.
    int cells = rows * columns, count = COVER_CACHE_SLOTS > cells ? COVER_CACHE_SLOTS : cells;
    snprintf(key, sizeof(key), "%s_count", name);
    if (configGetInt(themeConfig, key, &count) && count < cells)
        configSetInt(themeConfig, key, cells);

    mutable_image_t *image = initMutableImage(themePath, themeConfig, theme, name, elem->type, "COV", count, NULL, NULL);
    elem->extended = image;
    elem->endElem = &endMutableImage;
    if (image == NULL || image->cache == NULL) {
        LOG("THEMES Grid %s: NO cache, elem disabled !!\n", name);
        return;
    }
    elem->drawElem = &drawGrid;
    if (theme->grid != NULL)
        return;
    theme->grid = elem;
    theme->gridRows = rows;
    theme->gridColumns = columns;
    theme->gridSpacing = spacing < 0 ? 0 : spacing;
}
