// grid: the Grid view's shape limits, scrolling and Up/Down steps (include/grid.h).
#include "check.h"
#include "../../include/grid.h"

int main()
{
    // ---- shape: defaults for nonsense, caps, and never more than GRID_MAX_CELLS covers -------------
    int rows = 0, columns = 0;
    gridClamp(&rows, &columns);
    CHECK(rows == GRID_DEFAULT_ROWS && columns == GRID_DEFAULT_COLUMNS);
    rows = 9, columns = 9;
    gridClamp(&rows, &columns);
    CHECK(columns == GRID_MAX_COLUMNS && rows * columns <= GRID_MAX_CELLS && rows == 2);
    rows = 4, columns = 4;
    gridClamp(&rows, &columns);
    CHECK(rows == 4 && columns == 4);

    // ---- scrolling: the selected row stays in the middle, never past either end -------------------
    CHECK(gridTopRow(30, 0, 3, 4) == 0);  // first row
    CHECK(gridTopRow(30, 5, 3, 4) == 0);  // row 1 is already the middle row
    CHECK(gridTopRow(30, 13, 3, 4) == 2); // row 3 -> rows 2..4
    CHECK(gridTopRow(30, 29, 3, 4) == 5); // last row (7) -> rows 5..7, no blank rows below
    CHECK(gridTopRow(5, 4, 3, 4) == 0);   // a page shorter than the grid never scrolls
    CHECK(gridTopRow(1, 0, 3, 4) == 0);

    // ---- Up/Down: keep the column, a short last row takes its last cover, -1 leaves the grid ------
    CHECK(gridRowStep(10, 1, 4, -1) == -1); // top row: Up goes to the previous device menu
    CHECK(gridRowStep(10, 5, 4, -1) == 1);
    CHECK(gridRowStep(10, 1, 4, 1) == 5);
    CHECK(gridRowStep(10, 7, 4, 1) == 9);  // row 2 holds 8 and 9 only
    CHECK(gridRowStep(10, 9, 4, 1) == -1); // last row: Down goes to the next device menu
    CHECK(gridRowStep(10, 8, 4, -1) == 4);
    CHECK(gridRowStep(0, 0, 4, 1) == -1);   // empty page
    CHECK(gridRowStep(10, 12, 4, 1) == -1); // stale index

    TEST_DONE("grid");
}
