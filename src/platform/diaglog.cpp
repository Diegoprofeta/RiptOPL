/*
  The hardware log, ported from RIPPS2 build 115 (akilluminati47/RIPPS2, ripps2status.c). See include/diaglog.h.
  The platform layer, so the launch code can write to it; DIAG.TXT itself is core/diagsave.cpp.
*/

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <kernel.h>

#include "include/diaglog.h"

#define DIAG_SIZE (16 * 1024)

static char diagRing[DIAG_SIZE];
static int diagHead = 0, diagWrapped = 0;

void diagLog(const char *fmt, ...)
{
    char line[224];
    va_list ap;
    clock_t now = clock();
    int n, i, on;

    n = snprintf(line, sizeof(line), "%5d.%02d  ", (int)(now / CLOCKS_PER_SEC), (int)(now % CLOCKS_PER_SEC * 100 / CLOCKS_PER_SEC));
    va_start(ap, fmt);
    vsnprintf(line + n, sizeof(line) - n - 2, fmt, ap);
    va_end(ap);
    n = strlen(line);
    line[n++] = '\r';
    line[n++] = '\n';
    // DIntr says whether interrupts were on, so a caller that already turned them off keeps them off
    on = DIntr();
    for (i = 0; i < n; i++) {
        diagRing[diagHead++] = line[i];
        if (diagHead == DIAG_SIZE) {
            diagHead = 0;
            diagWrapped = 1;
        }
    }
    if (on)
        EIntr();
}

int diagCopy(char *out, int size, int *wrapped)
{
    int len, h, w, on, skip = 0;

    on = DIntr();
    h = diagHead;
    w = diagWrapped;
    len = w ? DIAG_SIZE : h;
    if (len > size) { // keep the newest lines
        skip = len - size;
        len = size;
    }
    if (w) {
        int start = (h + skip) % DIAG_SIZE, first = DIAG_SIZE - start;
        if (first > len)
            first = len;
        memcpy(out, diagRing + start, first);
        memcpy(out + first, diagRing, len - first);
    } else
        memcpy(out, diagRing + skip, len);
    if (on)
        EIntr();
    if (wrapped != NULL)
        *wrapped = w || skip > 0;
    return len;
}
