"""Execute C++ HDD mini-row selection and Neutrino's partition/argv copies."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else
          ROOT / "src/sources/hddsupport.cpp").read_text(encoding="utf-8")
system = (ROOT / "src/platform/sysneutrino.cpp").read_text(encoding="utf-8")
header = (ROOT / "include/hddsupport.h").read_text(encoding="utf-8")


def function(signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


launch = function("void HddSource::launch(")
start = launch.index("    if (gAutoLaunchGame == NULL) {\n        game =")
end = launch.index("    // D8:", start)
selection = launch[start:end]
signature = "static int hddResolveAutoLaunchGame("
resolver = function(signature) if signature in source else ""
if resolver:
    assert "hddGetHDLGamelist(&list)" in resolver and "hddFreeHDLGamelist(&list)" in resolver
    assert not any(s in resolver for s in ("fileXio", "hddWrite", "hddReadSectors", "delay("))
    assert launch.index("hddResolveAutoLaunchGame(game)") < launch.index("hddTryNeutrinoLaunch(game, configSet)")
types = header[header.index("typedef struct"):header.index("// HDD PS1/VCD")]
apa_copy = re.search(r'snprintf\(apaPart, sizeof\(apaPart\), "%s", game->partition_name\);', source).group(0)
dvd = re.search(r'snprintf\(filePath, sizeof\(filePath\), "-dvd=hdl:%s", path\);', system).group(0)
assert 'sysNeutrinoArgsPreflight("apa", apaPart,' in source

program = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
typedef unsigned char u8;
typedef unsigned int u32;
#define APA_IDMAX 32
#define HDL_GAME_NAME_MAX 64
#define LOG(...) ((void)0)
@TYPES@
static hdl_game_info_t rows[] = {
    {"PP.FIRST", "First", "SLUS_203.12", 0, 0, 0, 0, 0x14, 0, 0x104A00, 2097152},
    {"PP.SECOND", "Second", "SLES_535.05", 1, 2, 0x40, 4, 0x14, 1234, 0x20C800, 4194304},
};
static int scans, liveLists, frees, scanError, rowCount = 2;
int hddGetHDLGamelist(hdl_games_list_t *list) {
    ++scans;
    list->games = static_cast<hdl_game_info_t *>(malloc(sizeof(rows)));
    assert(list->games); memcpy(list->games, rows, sizeof(rows));
    list->count = rowCount; ++liveLists;
    return scanError; // Even a partially allocated failed walk must be freed.
}
void hddFreeHDLGamelist(hdl_games_list_t *list) {
    if (list->games) { free(list->games); --liveLists; ++frees; }
    list->games = nullptr; list->count = 0;
}
static hdl_game_info_t *gAutoLaunchGame;
static struct {
    hdl_game_info_t emptyHdl;
    hdl_game_info_t *activeHdl(int id) { return id == 0 ? &rows[0] : &emptyHdl; }
} gHddSupport;
@RESOLVER@
static int handoffs;
static hdl_game_info_t handed;
static char dvdArg[288];
static void launch(int id) {
    hdl_game_info_t *game;
    @SELECTION@
    // Same partition copy used by the Neutrino preflight, then its argv builder.
    char apaPart[APA_IDMAX + 1];
    @APA@
    const char *path = apaPart;
    char filePath[288];
    @DVD@
    snprintf(dvdArg, sizeof(dvdArg), "%s", filePath);
    handed = *game; ++handoffs; // Retain the rest of the resolved HDL metadata too.
}
static hdl_game_info_t mini(const char *startup, u32 sector) {
    hdl_game_info_t game = {};
    snprintf(game.startup, sizeof(game.startup), "%s", startup);
    game.start_sector = sector; return game;
}
static void reset() {
    assert(!liveLists); scans = frees = scanError = handoffs = 0; rowCount = 2;
    dvdArg[0] = 0; handed = {}; gAutoLaunchGame = nullptr;
}
int main() {
    reset(); auto game = mini("SLES_535.05", 0x20C800); gAutoLaunchGame = &game;
    launch(-1);
    assert(handoffs == 1 && !strcmp(dvdArg, "-dvd=hdl:PP.SECOND"));
    assert(scans == 1 && frees == 1 && !liveLists);
    assert(handed.start_sector == 0x20C800 && handed.total_size_in_kb == 4194304);
    assert(handed.layer_break == 1234 && handed.disctype == 0x14);
    assert(handed.dma_type == 0x40 && handed.dma_mode == 4);
    assert(handed.hdl_compat_flags == 1 && handed.ops2l_compat_flags == 2);
    reset(); game = mini("SLUS_999.99", 0x104A00); gAutoLaunchGame = &game; launch(-1);
    assert(handoffs == 1 && !strcmp(handed.startup, "SLUS_999.99")); // CFG already used argv startup
    assert(!strcmp(handed.partition_name, "PP.FIRST") && !strcmp(handed.name, "First"));
    reset(); game = mini("", 0x104A00); gAutoLaunchGame = &game; launch(-1);
    assert(handoffs == 1 && !strcmp(handed.startup, "SLUS_203.12"));
    for (u32 sector : {0u, 0x104A01u, 0xFFFFFFFFu}) {
        reset(); game = mini("SLUS_203.12", sector); gAutoLaunchGame = &game; launch(-1);
        assert(!handoffs && !game.partition_name[0] && !liveLists);
        assert(scans == (sector != 0) && frees == scans);
    }
    reset(); game = mini("SLUS_203.12", 0x104A00); scanError = -5; gAutoLaunchGame = &game; launch(-1);
    assert(!handoffs && scans == 1 && frees == 1 && !liveLists && !game.partition_name[0]);
    reset(); game = mini("SLUS_203.12", 0x104A00); rowCount = 0; gAutoLaunchGame = &game; launch(-1);
    assert(!handoffs && scans == 1 && frees == 1 && !liveLists && !game.partition_name[0]);
    reset(); game = rows[1]; gAutoLaunchGame = &game; launch(-1);
    assert(handoffs == 1 && scans == 0 && !strcmp(dvdArg, "-dvd=hdl:PP.SECOND"));
    reset(); launch(0);
    assert(handoffs == 1 && scans == 0 && !strcmp(dvdArg, "-dvd=hdl:PP.FIRST")); // menu hot path unchanged
    reset(); launch(-1); assert(!handoffs && scans == 0); // stale menu row
    puts("PASS: C++ HDD mini HDL resolution, metadata, argv startup, refusal and menu no-scan");
}
'''
for token, value in (("TYPES", types), ("RESOLVER", resolver), ("SELECTION", selection),
                     ("APA", apa_copy), ("DVD", dvd)):
    program = program.replace("@" + token + "@", value)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    cpp = path / "mini.cpp"
    exe = path / ("mini.exe" if sys.platform == "win32" else "mini")
    cpp.write_text(program, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(cpp), "-o", str(exe)], check=True, timeout=120)
    subprocess.run([str(exe)], check=True, timeout=10)
