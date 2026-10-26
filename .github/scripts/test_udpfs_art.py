"""Compile and exercise RiptOPL's UDPFS ART spelling resolver, and guard the art index's sweep.

A case-sensitive server keeps "art" and "ART" apart, and sbCreateFolders makes an empty "ART" beside a
user's "art". Discovery resolves the spelling once, before that folder is created, and retries until the
root lists completely (original #966-era ART discovery, retried from needsUpdate since #1037). The
per-image path must not enumerate anything. A partial directory listing must never be published as
proof that a cover does not exist.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
UDPFS = (ROOT / "src/sources/udpfssupport.cpp").read_text(encoding="utf-8")
INDEX = (ROOT / "src/sources/artindex.cpp").read_text(encoding="utf-8")
TEXCACHE = (ROOT / "src/gfx/texcache.cpp").read_text(encoding="utf-8")
failures = []


def function(source, signature):
    pos = source.find(signature)
    if pos < 0:
        raise AssertionError(f"Missing function: {signature}")
    start = source.find("{", pos)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[pos:i + 1]
    raise AssertionError(f"Unterminated function: {signature}")


get_image = function(UDPFS, "int UdpfsSource::image(")
init = function(UDPFS, "void UdpfsSource::init(")
update = function(UDPFS, "int UdpfsSource::update(")
needs_update = function(UDPFS, "int UdpfsSource::needsUpdate(")
waiter = function(UDPFS, "static void udpfsSetWaitingForServer(")
discover = function(UDPFS, "static void udpfsDiscoverArtFolder(void)")
folder_files = function(UDPFS, "static int udpfsArtFolderHasFiles(")
table = re.search(r"static const char \*const udpfsArtCaseNames\[8\] = \{.*?\};", UDPFS, re.S)

discover_call = needs_update.find("udpfsDiscoverArtFolder();")
if discover_call < 0 or discover_call > needs_update.find("\n        return"):
    failures.append("needsUpdate must retry ART discovery before any view-specific early return (#1037)")
if "!udpfsArtCaseChecked" not in waiter:
    failures.append("Unresolved ART must keep the general-refresh retry cadence alive (#1037)")
if not table:
    failures.append("ART casing table is missing")
if any(word in get_image for word in ("opendir(", "readdir(", "stat(", "udpfsDiscoverArtFolder(")):
    failures.append("The per-image hot path must not perform directory/network discovery")
if 'strcmp(folder, "ART")' not in get_image or "udpfsArtCaseNames[udpfsArtCaseIndex]" not in get_image:
    failures.append("Images must use the resolved ART spelling, and only for ART")
if "udpfsArtCaseChecked = 0;" not in init or "udpfsArtCaseIndex = 0;" not in init:
    failures.append("Reinitialization must reset ART resolution for a different share")
if not 0 <= update.find("udpfsDiscoverArtFolder();") < update.find("sbCreateFolders(udpfsPrefix, 1);"):
    failures.append("The case resolver must run BEFORE an empty uppercase ART can be created")
park = function(TEXCACHE, "GSTEXTURE *cacheGetTextureEx(")
if park.count("if (entry->failEpoch == gArtW.failEpoch) {") < 2:
    failures.append("Both absent-park paths must honour only the current fail generation (#1037)")

HARNESS = r"""
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#define MENU_UPD_DELAY_GENREFRESH 0
#define UDPFS_MODE_UPDATE_DELAY 300
typedef struct { int kind; int pos; } DIR;
struct dirent { char d_name[128]; };

static char udpfsPrefix[40] = "udpfs:/";
static int udpfsIomanModLoaded = 1, serverOnline = 1;
static int invalidations, indexInvalidations, rootOpens, folderOpens;
static int udpfsWaitingForServer, udpfsThemesScanned = 1, udpfsLanguagesScanned = 1;
static struct { int updateDelay; } instance;
#define udpfsInstance() (&instance)
static const char *rootNames[12];
static const char *folderNames[8][4];
static int rootReadError, folderOpenError[8], folderReadError[8], successfulReadErrno;
static DIR rootDir, folders[8];
static struct dirent returnedEntry;

@TABLE@
static volatile unsigned int udpfsArtCaseIndex;
static int udpfsArtCaseChecked;

static int udpfsServerAnswers(void) { return serverOnline; }
static void cacheInvalidateFailMemo(void) { invalidations++; }
static void artIndexInvalidate(void) { indexInvalidations++; }
@WAITER@
static DIR *opendir(const char *path)
{
    if (strcmp(path, "udpfs:/") == 0) {
        rootOpens++;
        rootDir.kind = -1;
        rootDir.pos = 0;
        return &rootDir;
    }
    for (int i = 0; i < 8; i++) {
        char full[40];
        snprintf(full, sizeof(full), "udpfs:/%s", udpfsArtCaseNames[i]);
        if (strcmp(path, full) == 0) {
            folderOpens++;
            if (folderOpenError[i]) { errno = ENOTDIR; return NULL; }
            folders[i].kind = i;
            folders[i].pos = 0;
            return &folders[i];
        }
    }
    errno = ENOENT;
    return NULL;
}
static struct dirent *readdir(DIR *dir)
{
    const char *name;
    if (dir->kind == -1) {
        name = rootNames[dir->pos++];
        if (!name && rootReadError)
            errno = EIO;
    } else {
        name = folderNames[dir->kind][dir->pos++];
        if (!name && folderReadError[dir->kind])
            errno = EIO;
    }
    if (name && successfulReadErrno)
        errno = EIO;
    if (!name)
        return NULL;
    snprintf(returnedEntry.d_name, sizeof(returnedEntry.d_name), "%s", name);
    return &returnedEntry;
}
static int closedir(DIR *dir) { (void)dir; return 0; }
@FOLDER@
@DISCOVER@

static int fails;
static void reset(void)
{
    memset(rootNames, 0, sizeof(rootNames));
    memset(folderNames, 0, sizeof(folderNames));
    memset(folderOpenError, 0, sizeof(folderOpenError));
    memset(folderReadError, 0, sizeof(folderReadError));
    udpfsArtCaseIndex = 0;
    udpfsArtCaseChecked = invalidations = indexInvalidations = rootOpens = folderOpens = 0;
    udpfsWaitingForServer = rootReadError = successfulReadErrno = 0;
    serverOnline = 1;
}
static void check(const char *label, int ok)
{
    if (!ok) {
        fprintf(stderr, "FAIL: %s\n", label);
        fails++;
    }
}
int main(void)
{
    reset();
    rootNames[0] = "ART";
    udpfsDiscoverArtFolder();
    check("canonical case", udpfsArtCaseChecked && udpfsArtCaseIndex == 0 &&
          invalidations == 1 && indexInvalidations == 1 && folderOpens == 0 && rootOpens == 1);

    reset();
    rootNames[0] = "art";
    udpfsDiscoverArtFolder();
    check("lowercase art resolves", udpfsArtCaseIndex == 7 && invalidations == 1);

    reset();
    rootNames[0] = "ART"; rootNames[1] = "art";
    folderNames[7][0] = "SLUS_123.45_COV.png";
    udpfsDiscoverArtFolder();
    check("populated lowercase wins over auto-created empty uppercase", udpfsArtCaseIndex == 7 && folderOpens <= 2);

    reset();
    rootNames[0] = "art"; rootNames[1] = "ART";
    folderNames[0][0] = "SLUS_123.45_COV.png";
    folderNames[7][0] = "SLUS_123.45_COV.png";
    udpfsDiscoverArtFolder();
    check("populated canonical spelling wins", udpfsArtCaseIndex == 0 && invalidations == 1 && folderOpens == 1);

    reset();
    rootNames[0] = "ART"; rootNames[1] = "Art"; rootNames[2] = "art";
    folderOpenError[3] = 1;
    folderNames[7][0] = "SLUS_123.45_COV.png";
    udpfsDiscoverArtFolder();
    check("failed open is not populated", udpfsArtCaseIndex == 7);

    reset();
    rootNames[0] = "Art"; rootNames[1] = "art";
    folderOpenError[3] = 1;
    udpfsDiscoverArtFolder();
    check("unusable preferred entry falls back to an empty directory", udpfsArtCaseIndex == 7);

    reset();
    rootNames[0] = "Art"; rootNames[1] = "art";
    folderOpenError[3] = folderOpenError[7] = 1;
    udpfsDiscoverArtFolder();
    check("all unusable entries fall back to canonical ART", udpfsArtCaseIndex == 0);

    reset();
    rootNames[0] = "art";
    folderOpenError[7] = 1;
    udpfsDiscoverArtFolder();
    check("single file masquerading as art is rejected", udpfsArtCaseIndex == 0);

    reset();
    rootNames[0] = "art";
    rootReadError = 1;
    udpfsDiscoverArtFolder();
    check("partial root enumeration is not latched", !udpfsArtCaseChecked && udpfsArtCaseIndex == 0);
    rootReadError = 0;
    udpfsDiscoverArtFolder();
    check("root enumeration may recover", udpfsArtCaseChecked && udpfsArtCaseIndex == 7);

    reset();
    rootNames[0] = "ART";
    successfulReadErrno = 1;
    udpfsDiscoverArtFolder();
    check("successful read errno does not poison EOF", udpfsArtCaseChecked && rootOpens == 1);
    udpfsDiscoverArtFolder();
    check("completed discovery does not rescan", rootOpens == 1);

    reset();
    rootNames[0] = "ART"; rootNames[1] = "art";
    folderReadError[0] = 1;
    folderNames[7][0] = "cover.png";
    udpfsDiscoverArtFolder();
    check("canonical scan error does not latch", !udpfsArtCaseChecked);
    folderReadError[0] = 0;
    udpfsDiscoverArtFolder();
    check("canonical scan recovers", udpfsArtCaseChecked && udpfsArtCaseIndex == 7);

    reset();
    rootNames[0] = "ART"; rootNames[1] = "art";
    folderReadError[7] = 1;
    udpfsDiscoverArtFolder();
    check("alternative scan error does not latch", !udpfsArtCaseChecked);

    reset();
    rootNames[0] = "art";
    folderReadError[7] = 1;
    udpfsDiscoverArtFolder();
    check("single candidate scan error does not latch", !udpfsArtCaseChecked);
    folderReadError[7] = 0;
    folderNames[7][0] = ".";
    successfulReadErrno = 1;
    udpfsDiscoverArtFolder();
    check("empty folder with successful-read errno is usable", udpfsArtCaseChecked && udpfsArtCaseIndex == 7);

    reset();
    serverOnline = 0;
    udpfsSetWaitingForServer(0);
    check("unresolved ART keeps polling after theme discovery", instance.updateDelay == MENU_UPD_DELAY_GENREFRESH);
    udpfsDiscoverArtFolder();
    check("offline share does not latch", !udpfsArtCaseChecked && rootOpens == 0);
    serverOnline = 1;
    udpfsDiscoverArtFolder();
    check("fresh share keeps the ART default", udpfsArtCaseChecked && udpfsArtCaseIndex == 0);
    check("completed ART retires the temporary cadence", instance.updateDelay == UDPFS_MODE_UPDATE_DELAY);

    if (!fails)
        puts("UDPFS ART: canonical, lowercase, duplicate casing, incomplete scans and retry cadence pass");
    return fails ? 1 : 0;
}
"""

if table:
    with tempfile.TemporaryDirectory() as directory:
        src = Path(directory) / "test.c"
        exe = Path(directory) / "test"
        src.write_text(HARNESS.replace("@TABLE@", table.group(0)).replace("@WAITER@", waiter)
                       .replace("@FOLDER@", folder_files).replace("@DISCOVER@", discover), encoding="utf-8")
        build = subprocess.run(["cc", "-std=gnu99", "-O0", "-Wall", "-Wextra", "-Werror", "-o", str(exe), str(src)],
                               capture_output=True, text=True, check=False)
        if build.returncode != 0:
            failures.append(f"UDPFS ART harness compilation failed:\n{build.stderr}")
        else:
            result = subprocess.run([str(exe)], capture_output=True, text=True, check=False)
            print(result.stdout, end="")
            if result.returncode != 0:
                failures.append(f"UDPFS ART harness assertions failed:\n{result.stderr}")

build_fn = function(INDEX, "ArtIndex::Dir *ArtIndex::build(")
if "errno = 0;" not in build_fn or "readError = errno;" not in build_fn:
    failures.append("The art index must distinguish end of directory from a readdir I/O error")
if not 0 <= build_fn.find("if (readError != 0)") < build_fn.find("slot->valid = 1;"):
    failures.append("An incomplete listing must be rejected before the slot is published")

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("UDPFS ART: resolver retried from needsUpdate, zero per-image I/O, art index rejects partial sweeps")
