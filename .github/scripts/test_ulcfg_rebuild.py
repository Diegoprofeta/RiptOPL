"""Deleting or renaming a USBLD game must never lose the other games' ul.cfg entries or split a game.

sbRebuildULCfg used to fopen ul.cfg with "wb" -- truncating every USBLD game's entry -- and ignore
fwrite and fclose, so a full device or a removed stick left a short or empty list. sbRename ignored
each part's rename, so a failure halfway left a game whose parts carried two names, and still wrote
the new name to ul.cfg. (The original, src/supportbase.c, has both defects.)

This compiles the real span of src/sources/supportbase.cpp (sbRebuildULCfg through sbRename) on the
host over a temporary folder, with fwrite, fclose and rename failures injected, and checks:

- a rebuild writes the list through ul.cfg.new and leaves no staged file behind;
- a failed write or close leaves ul.cfg byte for byte as it was, and no ul.cfg.new;
- a driver that refuses to rename onto an existing file still gets the new list; one whose renames
  all fail gets ul.cfg written directly, and only if that fails too do the parts keep the name
  ul.cfg.new lists; a ul.cfg that can be neither replaced nor removed keeps the old list;
- a rename whose second part fails puts the first part back and keeps the old name and ul.cfg;
- a rename whose ul.cfg rewrite fails puts every part back and keeps the old name.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'src/sources/supportbase.cpp').read_text(encoding='utf-8')
header = (root / 'include/supportbase.h').read_text(encoding='utf-8')
start = source.index('static int sbWriteULCfg(')
start = source.rindex('\n\n', 0, start)
end = source.index('\n}\n', source.index('void sbRename(')) + 3
span = source[start:end]
types = header[header.index('#define UL_GAME_NAME_MAX'):header.index('int isValidIsoName')]

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
typedef unsigned char u8;
typedef unsigned int u32;
#define SCECdPS2CD 0x12
#define FOLDER_SUB_MAX 64
static char sbBrowseSub[FOLDER_SUB_MAX + 1];
static u32 USBA_crc32(const char *s) { u32 h = 0; while (*s) h = h * 31 + (u8)*s++; return h; }
@TYPES@
#define LOG(...) ((void)0)
static int failWrite, failClose, refuseOverwrite, failUnlink, failRenameAt = -1, failRenameAlso = -1, renames;
static size_t fakeFwrite(const void *p, size_t s, size_t n, FILE *f) { return failWrite && --failWrite == 0 ? 0 : fwrite(p, s, n, f); }
static int fakeFclose(FILE *f) { int r = fclose(f); return failClose ? -1 : r; }
static int fakeRename(const char *a, const char *b)
{
    struct stat st;
    int n = renames++;
    if (n == failRenameAt || n == failRenameAlso || (refuseOverwrite && stat(b, &st) == 0))
        return -1;
    return rename(a, b);
}
static int fakeUnlink(const char *a) { size_t n = strlen(a); return failUnlink && n >= 6 && !strcmp(a + n - 6, "ul.cfg") ? -1 : unlink(a); }
#define fwrite fakeFwrite
#define fclose fakeFclose
#define rename fakeRename
#define unlink fakeUnlink
@SPAN@
#undef unlink
#undef rename
#undef fclose
#undef fwrite
static char dir[256];
static int failures;
#define CHECK(c, m) do { if (!(c)) { printf("FAIL: %s\n", m); failures++; } } while (0)
static long fileSize(const char *name) { char p[512]; struct stat st; snprintf(p, sizeof(p), "%s%s", dir, name); return stat(p, &st) == 0 ? st.st_size : -1; }
static void touch(const char *name) { char p[512]; snprintf(p, sizeof(p), "%s%s", dir, name); FILE *f = fopen(p, "wb"); fputs("x", f); fclose(f); }
static void game(base_game_info_t *g, const char *name, int parts) { memset(g, 0, sizeof(*g)); strcpy(g->name, name); strcpy(g->startup, "SLUS_123.45"); g->parts = parts; g->format = GAME_FORMAT_USBLD; }
static void partName(char *out, const base_game_info_t *g, const char *name, int part) { sbCreatePath_name(g, out, "", "/", part, name); }
int main(int argc, char **argv)
{
    snprintf(dir, sizeof(dir), "%s/", argv[1]);
    base_game_info_t games[3], *list = games;
    game(&games[0], "Alpha", 2); game(&games[1], "Beta", 1); game(&games[2], "Gamma", 1);
    const long entry = sizeof(USBExtreme_game_entry_t);

    CHECK(sbRebuildULCfg(&list, dir, 3, -1) == 0 && fileSize("ul.cfg") == 3 * entry && fileSize("ul.cfg.new") < 0, "rebuild writes every entry and removes ul.cfg.new");
    failWrite = 2;
    CHECK(sbRebuildULCfg(&list, dir, 3, 1) == -1 && fileSize("ul.cfg") == 3 * entry && fileSize("ul.cfg.new") < 0, "a failed write keeps ul.cfg intact");
    failWrite = 0; failClose = 1;
    CHECK(sbRebuildULCfg(&list, dir, 3, 1) == -1 && fileSize("ul.cfg") == 3 * entry && fileSize("ul.cfg.new") < 0, "a failed close keeps ul.cfg intact");
    failClose = 0; refuseOverwrite = 1;
    CHECK(sbRebuildULCfg(&list, dir, 3, 1) == 0 && fileSize("ul.cfg") == 2 * entry && fileSize("ul.cfg.new") < 0, "no rename onto an existing file still replaces the list");
    refuseOverwrite = 0;
    sbRebuildULCfg(&list, dir, 3, -1);

    char path[256], other[256];
    for (int part = 0; part < 2; part++) { partName(path, &games[0], "Alpha", part); touch(path); }
    renames = 0; failRenameAt = 1;
    sbRename(&list, dir, "/", 3, 0, (char *)"Omega");
    CHECK(strcmp(games[0].name, "Alpha") == 0, "a failed part rename keeps the old name");
    for (int part = 0; part < 2; part++) {
        partName(path, &games[0], "Alpha", part); partName(other, &games[0], "Omega", part);
        CHECK(fileSize(path) == 1 && fileSize(other) < 0, "every part is back under the old name");
    }
    renames = 0; failRenameAt = -1; failWrite = 1; // parts rename, then the ul.cfg write fails
    sbRename(&list, dir, "/", 3, 0, (char *)"Omega");
    failWrite = 0;
    CHECK(strcmp(games[0].name, "Alpha") == 0 && fileSize("ul.cfg") == 3 * entry, "a failed ul.cfg rewrite keeps the old name and list");
    for (int part = 0; part < 2; part++) {
        partName(path, &games[0], "Alpha", part);
        CHECK(fileSize(path) == 1, "a failed ul.cfg rewrite puts the parts back");
    }
    renames = 0;
    sbRename(&list, dir, "/", 3, 0, (char *)"Omega");
    partName(path, &games[0], "Omega", 1);
    CHECK(strcmp(games[0].name, "Omega") == 0 && fileSize(path) == 1 && fileSize("ul.cfg") == 3 * entry, "a clean rename renames every part and rewrites ul.cfg");
    renames = 0; failRenameAt = 2; failRenameAlso = 3; // parts rename; both ul.cfg.new renames fail
    sbRename(&list, dir, "/", 3, 0, (char *)"Delta");
    failRenameAt = failRenameAlso = -1;
    partName(path, &games[0], "Delta", 1);
    CHECK(strcmp(games[0].name, "Delta") == 0 && fileSize(path) == 1 && fileSize("ul.cfg") == 3 * entry && fileSize("ul.cfg.new") < 0,
          "a driver with no working rename gets ul.cfg written directly");
    renames = 0; failRenameAt = 2; failRenameAlso = 3; failWrite = 4; // and the direct write fails too
    sbRename(&list, dir, "/", 3, 0, (char *)"Sigma");
    failRenameAt = failRenameAlso = -1; failWrite = 0;
    partName(path, &games[0], "Sigma", 1);
    CHECK(strcmp(games[0].name, "Sigma") == 0 && fileSize(path) == 1 && fileSize("ul.cfg.new") == 3 * entry,
          "with ul.cfg gone and unwritable, the parts keep the name ul.cfg.new lists");
    sbRebuildULCfg(&list, dir, 3, -1);
    renames = 0; refuseOverwrite = 1; failUnlink = 1; // a read-only ul.cfg: no rename onto it, no unlink
    sbRename(&list, dir, "/", 3, 0, (char *)"Kappa");
    refuseOverwrite = failUnlink = 0;
    partName(path, &games[0], "Sigma", 1); partName(other, &games[0], "Kappa", 1);
    CHECK(strcmp(games[0].name, "Sigma") == 0 && fileSize(path) == 1 && fileSize(other) < 0 && fileSize("ul.cfg") == 3 * entry && fileSize("ul.cfg.new") < 0,
          "a ul.cfg that cannot be removed keeps the old list, and the parts go back");
    return failures != 0;
}
'''

with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    data = work / 'device'
    data.mkdir()
    program = HARNESS.replace('@TYPES@', types).replace('@SPAN@', span)
    (work / 'harness.cpp').write_text(program, encoding='utf-8')
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Werror', '-Wno-unused-function', str(work / 'harness.cpp'), '-o', str(work / 'harness')], check=True)
    result = subprocess.run([str(work / 'harness'), str(data)], capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.exit(1)
print('PASS: ul.cfg is replaced only by a complete list, and a failed rename leaves the game whole')
