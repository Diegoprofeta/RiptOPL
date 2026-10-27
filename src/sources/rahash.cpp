/*
  RA: the image hash, computed the way RetroAchievements computes it.

  Algorithm (rc_hash_ps2 in rcheevos, hash_disc.c):
    1. open the image and read SYSTEM.CNF
    2. take the boot executable name from BOOT2, e.g. "SLUS_210.65"
    3. MD5( ASCII(name) || contents of that file )

  Half of the work already exists in OPL: ps2cnf.c parses SYSTEM.CNF and
  GetStartupExecName extracts the name and strips "cdrom0:\". The caller
  already holds that name as game->startup, so what remains here is reading the
  file itself and running MD5 over it.

  PS1 VCDs follow rc_hash_psx: the BOOT line of SYSTEM.CNF (or PSX.EXE), and
  the PS-X EXE header's own size.

  Hashing on the console means the images themselves decide which games are
  supported; nothing on the PC has to be prepared or kept in sync.

  Upstream design and implementation: hacan359. Image files, VCDs, HDLoader
  partitions and physical discs share the ISO9660 walker and hash algorithm.
*/

#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>

#include "include/opl.h"
#include "include/util.h"
#include "include/iosupport.h"
#include "include/system.h"
#include "include/supportbase.h"
#include "include/ioman.h"
#include "include/md5.h"
#include "include/hdd.h"
#include "include/hdl_layout.h"
#include "include/rahash.h"

#include "include/ps2sdkapi_compat.h" // lseek64: images can exceed 2 GB

/* Same cap as rcheevos: no boot executable is larger */
constexpr int RA_HASH_MAX_EXEC = (64 * 1024 * 1024);
constexpr int RA_HASH_CHUNK = (64 * 1024);

/* Scratch buffer for the ISO9660 walker (one chunk of the executable, one
   sector of a directory). File-scope on purpose: the source-scraping test
   harness reaches in and calls disc_read_at() with this buffer, and a 64 KB
   64-byte-aligned buffer is better kept out of the object. */
static char g_chunk[RA_HASH_CHUNK] __attribute__((aligned(64)));

/* Where the ISO9660 sectors come from. */
enum RaSrcKind { RA_SRC_ISO,
                 RA_SRC_VCD,
                 RA_SRC_DISC,
                 RA_SRC_HDL };
struct RaSrc
{
    int fd;
    RaSrcKind kind;
    const hdl_layout_header_t *hdl;
};

/* The image hash, computed the way RetroAchievements computes it. File-local
   class: test_ra_disc.py compiles this file with its #include lines stripped,
   so the class has to be defined here rather than in a header. One instance
   (gRaHash); the raHash* entry points below are thin forwarders, and
   disc_read_at stays a file-scope forwarder for the test harness. */
class RaHash
{
public:
    /* Where to report hashing steps. Set by the caller. */
    void setStepLog(ra_step_fn fn) { step_ = fn; }

    /* Hashes the boot executable of an image WITHOUT mounting it: walks ISO9660
       with 64-bit offsets, because a mounted image on USB hangs when reading files
       beyond the 2 GB mark. out33 receives 32 hex digits plus the terminator.
       Returns 0 on success. */
    int hashIsoDirect(const char *isopath, const char *startup, char *out33);

    /* The same boot executable through the ROM filesystem first; direct
       sector reads are the fallback. */
    int hashDisc(const char *bootPath, const char *startup, char *out33);

    int hashHdl(unsigned int start_sector, const char *startup, char *out33);
    int hashVcd(const char *vcdpath, char *boot, int boot_max, char *out33);
    int vcdBootName(const char *vcdpath, char *boot, int boot_max);

    /* Read whole sectors into the caller's aligned buffer (see the comment
       at the file-scope disc_read_at forwarder). */
    int discReadAt(long long off, void *buf, int len);

private:
    void step(const char *what);
    void stepNum(const char *what, unsigned int a, unsigned int b, int c);
    int discReadSectors(unsigned int lba, unsigned int count, void *buf);
    int readAt(const RaSrc &src, long long off, void *buf, int len);
    /* Finds a directory entry. Returns 0 and fills lba/size. */
    int findEntry(const RaSrc &src, unsigned int dir_lba, unsigned int dir_size,
                  const char *want, unsigned int *out_lba, unsigned int *out_size);
    /* A path under the root, parts split by '\', e.g. "DATA\MAIN.EXE". */
    int findPath(const RaSrc &src, const char *path, unsigned int *out_lba, unsigned int *out_size);
    /* Root directory of the volume. */
    int readRoot(const RaSrc &src, unsigned int *root_lba, unsigned int *root_size);
    /* MD5( name || contents of that file ), the way RetroAchievements does it. */
    int hashBootExec(const RaSrc &src, const char *startup, char *out33);
    int psxBootName(const RaSrc &src, char *boot, int boot_max);
    int hashPsx(const RaSrc &src, char *boot, int boot_max, char *out33);

    ra_step_fn step_ = NULL;
};

static RaHash gRaHash;

void raHashSetStepLog(ra_step_fn fn)
{
    gRaHash.setStepLog(fn);
}

int raHashIsoDirect(const char *isopath, const char *startup, char *out33)
{
    return gRaHash.hashIsoDirect(isopath, startup, out33);
}

int raHashDisc(const char *bootPath, const char *startup, char *out33)
{
    return gRaHash.hashDisc(bootPath, startup, out33);
}

int raHashHdl(unsigned int start_sector, const char *startup, char *out33)
{
    return gRaHash.hashHdl(start_sector, startup, out33);
}

int raHashVcd(const char *vcdpath, char *boot, int boot_max, char *out33)
{
    return gRaHash.hashVcd(vcdpath, boot, boot_max, out33);
}

int raVcdBootName(const char *vcdpath, char *boot, int boot_max)
{
    return gRaHash.vcdBootName(vcdpath, boot, boot_max);
}

/* Read whole sectors into the caller's aligned buffer. The image walker uses
   sector-aligned offsets and buffers large enough for the rounded-up tail;
   return only the requested byte count so padding never enters the hash. */
static int disc_read_at(long long off, void *buf, int len)
{
    return gRaHash.discReadAt(off, buf, len);
}

void RaHash::step(const char *what)
{
    if (step_ != NULL)
        step_(what);
}

/* A crumb with numbers in it. */
void RaHash::stepNum(const char *what, unsigned int a, unsigned int b, int c)
{
    char line[64];

    snprintf(line, sizeof(line), "%s lba=%u n=%u rv=%d", what, a, b, c);
    step(line);
}

/* 32 lowercase hex digits and the terminator. */
static void md5_hex(const md5_byte_t *digest, char *out33)
{
    static const char hex[] = "0123456789abcdef";
    int i;

    for (i = 0; i < 16; i++) {
        out33[i * 2] = hex[(digest[i] >> 4) & 0xF];
        out33[i * 2 + 1] = hex[digest[i] & 0xF];
    }
    out33[32] = '\0';
}

/* ------------------------------------------------------------------ */
/* Direct image read, no mounting                                      */

/*
  Mounting through "iso:" on USB hangs on the first read when the boot
  executable sits beyond the 2 GB mark of the image, past the reach of a signed
  32-bit offset. The same image works from a share.

  So we bypass the driver: open the image as a plain file, walk the ISO9660
  directory ourselves and seek with 64-bit lseek64.

  This also reads far less than mounting does: one volume descriptor sector, the
  root directory (usually a couple of kilobytes) and the executable itself.

  Do NOT "simplify" this back to a mount plus a normal open/read -- that is the
  bug it exists to avoid.
*/

constexpr int ISO_SECTOR = 2048;
constexpr int ISO_PVD_LBA = 16;

static unsigned int le32(const unsigned char *p)
{
    return (unsigned int)p[0] | ((unsigned int)p[1] << 8) |
           ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}

constexpr int DISC_READ_TRIES = 16;
constexpr int DISC_READ_NOM_TRIES = 8;

int RaHash::discReadSectors(unsigned int lba, unsigned int count, void *buf)
{
    sceCdRMode mode;
    int attempt, rv, err = SCECdErNO;

    mode.trycount = 32;
    mode.datapattern = SCECdSecS2048;
    mode.pad = 0;

    for (attempt = 0; attempt < DISC_READ_TRIES; attempt++) {
        mode.spindlctrl = attempt < DISC_READ_NOM_TRIES ? SCECdSpinNom : SCECdSpinStm;

        sceCdDiskReady(0);

        rv = sceCdRead(lba, count, buf, &mode);
        if (!rv) {
            /* Refused before it started: drive not ready or a command
               still pending. Worth another go after DiskReady. */
            err = -1;
            continue;
        }

        sceCdSync(0);

        err = sceCdGetError();
        if (err == SCECdErNO) {
            if (attempt > 0)
                stepNum("cd-read-ok-after-retries", lba, count, attempt);
            return 0;
        }
    }

    stepNum("cd-read-error", lba, count, err);
    return -1;
}

int RaHash::discReadAt(long long off, void *buf, int len)
{
    unsigned int lba, sectors;

    if (len <= 0)
        return -1;

    if ((off % ISO_SECTOR) != 0) { /* never happens; a guard, not logic */
        stepNum("cd-read-unaligned", (unsigned int)off, (unsigned int)len, 0);
        return -1;
    }

    lba = (unsigned int)(off / ISO_SECTOR);
    sectors = (unsigned int)((len + ISO_SECTOR - 1) / ISO_SECTOR);

    if (discReadSectors(lba, sectors, buf) != 0)
        return -1;

    return len;
}

/* A VCD is a raw 2352-byte-sector image behind a 1 MB POPStarter header;
   the 2048 data bytes of each sector start 24 bytes in. */
constexpr long long VCD_HEADER = 0x100000;
constexpr int VCD_RAW_SECTOR = 2352;
constexpr int VCD_DATA_OFF = 24;

static int vcd_read_at(int fd, long long off, void *buf, int len)
{
    int done = 0;

    while (done < len) {
        long long pos = off + done;
        long long lba = pos / ISO_SECTOR;
        int in = (int)(pos % ISO_SECTOR);
        int want = ISO_SECTOR - in;
        int got;

        if (want > len - done)
            want = len - done;

        if (lseek64(fd, VCD_HEADER + lba * VCD_RAW_SECTOR + VCD_DATA_OFF + in, SEEK_SET) < 0)
            return -1;

        got = read(fd, (char *)buf + done, want);
        if (got <= 0)
            return done > 0 ? done : -1;

        done += got;
        if (got < want)
            break;
    }

    return done;
}

/* HDLoader maps ISO logical sectors through the descriptor at the head
   of the APA game partition, just as CDVDMAN's DeviceReadSectors does. This
   reader never mounts a partition, touches metadata or writes ATA sectors.
   Reject invalid/overlapping physical or logical extents before hashing. */
static int hdl_valid_map(const hdl_layout_header_t *map)
{
    int i, j;

    if (map->num_partitions < 1 || map->num_partitions > HDL_LAYOUT_PARTS)
        return 0;
    for (i = 0; i < map->num_partitions; i++) {
        const hdl_layout_part_t *a = &map->part_specs[i];
        unsigned int count, raw_count;
        if (!a->part_size || a->part_size % ISO_SECTOR)
            return 0;
        count = a->part_size / ISO_SECTOR;
        raw_count = a->part_size / 512;
        if (count > 0xffffffffU - a->part_offset ||
            raw_count > 0xffffffffU - a->data_start)
            return 0;
        for (j = 0; j < i; j++) {
            const hdl_layout_part_t *b = &map->part_specs[j];
            unsigned int other_count = b->part_size / ISO_SECTOR;
            unsigned int other_raw_count = b->part_size / 512;
            if (a->part_offset < b->part_offset + other_count &&
                b->part_offset < a->part_offset + count)
                return 0;
            if (a->data_start < b->data_start + other_raw_count &&
                b->data_start < a->data_start + raw_count)
                return 0;
        }
    }
    return 1;
}

/* Eight KiB per bounded read amortizes the expensive EE/IOP fileXio
   round trip over up to four adjacent ISO sectors, without assuming that
   adjacent logical sectors from two APA partitions are physically adjacent. */
constexpr unsigned int HDL_READ_SECTORS = 4;
static unsigned char g_hdl_sector[HDL_READ_SECTORS * ISO_SECTOR] __attribute__((aligned(64)));

static int hdl_read_at(const hdl_layout_header_t *map, long long off, void *buf, int len)
{
    int done = 0;
    if (!map || off < 0 || len <= 0)
        return -1;

    while (done < len) {
        unsigned long long position = (unsigned long long)off + done;
        unsigned long long sector = position / ISO_SECTOR;
        unsigned int within = (unsigned int)(position % ISO_SECTOR);
        unsigned int raw_lba = 0, batch = 0;
        int n, i, found = 0;

        if (sector > 0xffffffffU)
            return -1;
        for (i = 0; i < map->num_partitions; i++) {
            const hdl_layout_part_t *part = &map->part_specs[i];
            unsigned int count = part->part_size / ISO_SECTOR;
            if (sector >= part->part_offset &&
                sector - part->part_offset < count) {
                unsigned int relative = (unsigned int)(sector - part->part_offset);
                raw_lba = part->data_start + (relative << 2);
                batch = count - relative;
                if (batch > HDL_READ_SECTORS)
                    batch = HDL_READ_SECTORS;
                found = 1;
                break;
            }
        }
        if (!found || !batch ||
            hddReadSectors(raw_lba, batch * 4, g_hdl_sector) != 0)
            return -1;

        n = batch * ISO_SECTOR - within;
        if (n > len - done)
            n = len - done;
        memcpy((unsigned char *)buf + done, g_hdl_sector + within, n);
        done += n;
    }
    return done;
}

int RaHash::readAt(const RaSrc &src, long long off, void *buf, int len)
{
    if (src.kind == RA_SRC_DISC)
        return disc_read_at(off, buf, len);
    if (src.kind == RA_SRC_VCD)
        return vcd_read_at(src.fd, off, buf, len);
    if (src.kind == RA_SRC_HDL)
        return hdl_read_at(src.hdl, off, buf, len);

    if (lseek64(src.fd, off, SEEK_SET) < 0)
        return -1;

    return read(src.fd, buf, len);
}

/* Finds a directory entry. Returns 0 and fills lba/size. */
int RaHash::findEntry(const RaSrc &src, unsigned int dir_lba, unsigned int dir_size,
                      const char *want, unsigned int *out_lba, unsigned int *out_size)
{
    unsigned int done = 0;

    while (done < dir_size) {
        int got = readAt(src, (long long)(dir_lba)*ISO_SECTOR + done, g_chunk, ISO_SECTOR);
        int p = 0;
        /* Parse only as far as the DIRECTORY runs, which is not always as far as the sector we
           just read. A well-formed ISO9660 sizes every directory extent in whole 2048-byte
           blocks, so on a good image this is always ISO_SECTOR -- but a damaged or hand-built
           image can end its extent mid-sector, and the bytes after it belong to whatever file
           follows. Parsing those would let adjacent image data pose as a directory record,
           match the name we are looking for, and hand back its LBA: raHashIsoDirect then hashes
           the wrong file and reports a confident, wrong game id. The read stays a full sector
           on purpose -- clamping it too would turn a truncated image into a hard failure that
           did not happen before, and bounding the PARSE is what actually fixes this. */
        unsigned int left = dir_size - done;
        int limit = (left < (unsigned int)ISO_SECTOR) ? (int)left : ISO_SECTOR;

        if (got != ISO_SECTOR)
            return -1;

        while (p < limit) {
            unsigned char *rec = (unsigned char *)&g_chunk[p];
            int len = rec[0];
            int namelen;

            if (len == 0)
                break; /* entries never cross a sector boundary */

            /* ...which the format promises and a damaged image does not. Without this the
               walk trusts len blindly: rec[32] and the name bytes at rec[33 + i] read up to
               ~287 bytes past p, and since only the first ISO_SECTOR of g_chunk was filled
               that is leftover data from an earlier 64 KB read -- so a truncated image can
               match a name that is not there and hand back a bogus LBA. Bounded by `limit`,
               not ISO_SECTOR: a record must fit inside the directory, not merely inside the
               buffer the directory was read into. */
            if (len < 33 || p + len > limit)
                break;

            namelen = rec[32];

            /* The name must also fit inside the record it claims to belong to. */
            if (33 + namelen > len)
                break;

            /* The name in the image carries a version: "SLUS_210.65;1".
               Compare up to the semicolon so the version does not matter, and
               without case, as rcheevos does: a PS1 SYSTEM.CNF may name its
               executable in lower case. */
            if (namelen > 0) {
                int i, same = 1;

                for (i = 0; i < namelen && want[i] != '\0'; i++) {
                    if (tolower(rec[33 + i]) != tolower((unsigned char)want[i])) {
                        same = 0;
                        break;
                    }
                }

                if (same && want[i] == '\0' &&
                    (i == namelen || rec[33 + i] == ';')) {
                    *out_lba = le32(&rec[2]);
                    *out_size = le32(&rec[10]);
                    return 0;
                }
            }

            p += len;
        }

        done += ISO_SECTOR;
    }

    return -2;
}

/* Root directory of the volume. */
int RaHash::readRoot(const RaSrc &src, unsigned int *root_lba, unsigned int *root_size)
{
    static unsigned char pvd[ISO_SECTOR] __attribute__((aligned(64)));

    /* Primary volume descriptor: sector 16, "CD001" at offset 1 */
    if (readAt(src, (long long)ISO_PVD_LBA * ISO_SECTOR, pvd, ISO_SECTOR) != ISO_SECTOR ||
        pvd[1] != 'C' || pvd[2] != 'D' || pvd[3] != '0' || pvd[4] != '0' || pvd[5] != '1') {
        step("2-no-cd001");
        return -1;
    }
    step("2-cd001-found");

    /* The root directory record lives inside the descriptor at offset 156 */
    *root_lba = le32(&pvd[156 + 2]);
    *root_size = le32(&pvd[156 + 10]);
    stepNum("2-root", *root_lba, *root_size, 0);

    return 0;
}

/* MD5( name || contents of that file ), the way RetroAchievements does it. */
int RaHash::hashBootExec(const RaSrc &src, const char *startup, char *out33)
{
    md5_state_t md5;
    md5_byte_t digest[16];
    unsigned int root_lba, root_size, elf_lba, elf_size, left;
    long long off;

    if (readRoot(src, &root_lba, &root_size) != 0)
        return -2;

    if (findEntry(src, root_lba, root_size, startup, &elf_lba, &elf_size) != 0) {
        step("3-elf-not-in-directory");
        return -3;
    }
    step("3-elf-found");

    if (elf_size == 0 || elf_size > RA_HASH_MAX_EXEC) {
        step("3-odd-elf-size");
        return -4;
    }

    md5_init(&md5);
    md5_append(&md5, (const md5_byte_t *)startup, (int)strlen(startup));

    off = (long long)elf_lba * ISO_SECTOR;
    left = elf_size;
    step("4-reading-elf-directly");

    while (left > 0) {
        int want = left > RA_HASH_CHUNK ? RA_HASH_CHUNK : (int)left;
        int got = readAt(src, off, g_chunk, want);

        if (got <= 0) {
            step("4-read-broke-off");
            return -5;
        }

        md5_append(&md5, (const md5_byte_t *)g_chunk, got);
        off += got;
        left -= (unsigned int)got;
    }

    md5_finish(&md5, digest);
    md5_hex(digest, out33);

    step("5-hashed-directly");
    LOG("RA: direct hash %s = %s (%u bytes)\n", startup, out33, elf_size);

    return 0;
}

int RaHash::hashIsoDirect(const char *isopath, const char *startup, char *out33)
{
    int ret;
    RaSrc src = {-1, RA_SRC_ISO, NULL};

    if (isopath == NULL || startup == NULL || out33 == NULL)
        return -1;

    out33[0] = '\0';

    step("1-opening-image");
    src.fd = open(isopath, O_RDONLY);
    if (src.fd < 0) {
        /* open() always answers -1: ps2sdk's __transform_errno puts the IOP code in errno.
           On a share that code is the whole story -- EBUSY is smbman saying an earlier run
           still holds the image (see modules/network/smbman-ra), which is worth telling the
           user apart from "could not open it", because it is something they can act on. */
        int err = errno;
        char line[48];

        snprintf(line, sizeof(line), "1-open-failed errno=%d", err);
        step(line);
        return err == EBUSY ? -6 : -1;
    }

    ret = hashBootExec(src, startup, out33);
    close(src.fd);

    return ret;
}

/* Automatic PS2 RA hashing for an installed HDLoader APA game. Read-only
   access through the already resident HDD device; no conversion to ISO,
   partition writes, cache flushing or extra mount. The same ISO9660 walker
   and boot-executable MD5 algorithm as a normal image are reused. */
int RaHash::hashHdl(unsigned int start_sector, const char *startup, char *out33)
{
    static hdl_layout_header_t header __attribute__((aligned(64)));
    RaSrc src = {-1, RA_SRC_HDL, &header};
    int result;

    if (!startup || !startup[0] || !out33)
        return -1;
    out33[0] = '\0';
    if (start_sector == 0 || hddReadSectors(start_sector, 2, &header) != 0)
        return -1;
    /* The selected HDL entry's boot executable must match the descriptor
       read from this exact installed partition. A stale list or an ATA
       re-enumeration must never hash a different game's executable. */
    if (strncmp(startup, header.startup, sizeof(header.startup)) != 0) {
        step("hdl-stale-startup");
        return -2;
    }
    if (!hdl_valid_map(&header)) {
        step("hdl-invalid-map");
        return -2;
    }
    result = hashBootExec(src, startup, out33);
    if (result != 0)
        out33[0] = '\0';
    return result;
}

// Hash the same boot executable through the ROM filesystem first. Exact length
// checks reject a truncated read instead of identifying a partial executable.
int RaHash::hashDisc(const char *bootPath, const char *startup, char *out33)
{
    static const RaSrc disc = {-1, RA_SRC_DISC, NULL};
    md5_state_t md5;
    md5_byte_t digest[16];
    int fd, size, left, ret = -1;

    if (bootPath == NULL || startup == NULL || out33 == NULL)
        return -1;
    out33[0] = '\0';
    fd = open(bootPath, O_RDONLY);
    if (fd >= 0) {
        size = lseek(fd, 0, SEEK_END);
        if (size > 0 && size <= RA_HASH_MAX_EXEC && lseek(fd, 0, SEEK_SET) == 0) {
            md5_init(&md5);
            md5_append(&md5, (const md5_byte_t *)startup, strlen(startup));
            left = size;
            while (left > 0) {
                int want = left > RA_HASH_CHUNK ? RA_HASH_CHUNK : left;
                int got = read(fd, g_chunk, want);
                if (got <= 0 || got > want)
                    break;
                md5_append(&md5, (const md5_byte_t *)g_chunk, got);
                left -= got;
            }
            if (left == 0) {
                md5_finish(&md5, digest);
                md5_hex(digest, out33);
                ret = 0;
            }
        }
        close(fd);
    }
    if (ret == 0)
        return 0;

    // Some ROM file drivers cannot read an extent that direct sector reads can.
    return hashBootExec(disc, startup, out33);
}

/* ------------------------------------------------------------------ */
/* PS1 through POPS (rc_hash_psx in rcheevos)                         */

int RaHash::findPath(const RaSrc &src, const char *path, unsigned int *out_lba, unsigned int *out_size)
{
    unsigned int lba, size;
    char part[64];

    if (readRoot(src, &lba, &size) != 0)
        return -1;

    while (*path == '\\')
        path++;

    while (*path != '\0') {
        int n = 0;

        while (path[n] != '\0' && path[n] != '\\')
            n++;
        if (n >= (int)sizeof(part))
            return -2;

        memcpy(part, path, n);
        part[n] = '\0';

        if (findEntry(src, lba, size, part, &lba, &size) != 0)
            return -2;

        path += n;
        while (*path == '\\')
            path++;
    }

    *out_lba = lba;
    *out_size = size;
    return 0;
}

/* "BOOT = cdrom:\SLUS_012.15;1" -> "SLUS_012.15". As in rcheevos, only a
   line that starts with BOOT counts, and BOOT2 does not. */
static int parse_boot_psx(const char *cnf, char *out, int max)
{
    const char *p = cnf;

    while (*p != '\0') {
        if (strncmp(p, "BOOT", 4) == 0) {
            const char *q = p + 4;

            while (*q == ' ' || *q == '\t')
                q++;

            if (*q == '=') {
                int len = 0;

                q++;
                while (*q == ' ' || *q == '\t')
                    q++;
                if (strncmp(q, "cdrom:", 6) == 0)
                    q += 6;
                while (*q == '\\')
                    q++;

                while (q[len] != '\0' && q[len] != ';' && q[len] != ' ' &&
                       q[len] != '\t' && q[len] != '\r' && q[len] != '\n')
                    len++;

                if (len <= 0 || len >= max)
                    return -7;

                memcpy(out, q, len);
                out[len] = '\0';
                return 0;
            }
        }

        while (*p != '\0' && *p != '\n')
            p++;
        if (*p == '\n')
            p++;
    }

    return -5;
}

int RaHash::psxBootName(const RaSrc &src, char *boot, int boot_max)
{
    static char cnf[ISO_SECTOR];
    unsigned int lba, size;
    int got;

    boot[0] = '\0';

    if (findPath(src, "SYSTEM.CNF", &lba, &size) != 0 || size == 0)
        return -2;
    if (size > sizeof(cnf) - 1)
        size = sizeof(cnf) - 1;

    got = readAt(src, (long long)lba * ISO_SECTOR, cnf, (int)size);
    if (got <= 0)
        return -4;
    cnf[got] = '\0';

    return parse_boot_psx(cnf, boot, boot_max);
}

int RaHash::hashPsx(const RaSrc &src, char *boot, int boot_max, char *out33)
{
    unsigned char head[32];
    unsigned int lba, size, left;
    md5_state_t md5;
    md5_byte_t digest[16];
    long long off;

    if (psxBootName(src, boot, boot_max) != 0 || findPath(src, boot, &lba, &size) != 0) {
        /* the BIOS falls back to PSX.EXE, and so does rcheevos */
        if (boot_max < (int)sizeof("PSX.EXE") || findPath(src, "PSX.EXE", &lba, &size) != 0) {
            step("3-psx-no-exe");
            return -3;
        }
        strcpy(boot, "PSX.EXE");
    }
    step("3-psx-exe-found");

    /* the size in the PS-X EXE header leaves out the 2048-byte header */
    off = (long long)lba * ISO_SECTOR;
    if (readAt(src, off, head, sizeof(head)) != sizeof(head))
        return -5;
    if (memcmp(head, "PS-X EXE", 8) == 0) {
        unsigned int payload = le32(&head[28]);
        if (payload > RA_HASH_MAX_EXEC - ISO_SECTOR)
            return -4;
        size = payload + ISO_SECTOR;
    }

    if (size == 0 || size > RA_HASH_MAX_EXEC) {
        step("3-odd-exe-size");
        return -4;
    }

    md5_init(&md5);
    md5_append(&md5, (const md5_byte_t *)boot, (int)strlen(boot));

    left = size;
    while (left > 0) {
        int want = left > RA_HASH_CHUNK ? RA_HASH_CHUNK : (int)left;
        int got = readAt(src, off, g_chunk, want);

        if (got <= 0) {
            step("4-read-broke-off");
            return -5;
        }

        md5_append(&md5, (const md5_byte_t *)g_chunk, got);
        off += got;
        left -= (unsigned int)got;
    }

    md5_finish(&md5, digest);
    md5_hex(digest, out33);

    step("5-psx-hashed");
    LOG("RA: psx hash %s = %s (%u bytes)\n", boot, out33, size);

    return 0;
}

int RaHash::vcdBootName(const char *vcdpath, char *boot, int boot_max)
{
    RaSrc src = {open(vcdpath, O_RDONLY), RA_SRC_VCD, NULL};
    unsigned int lba, size;
    int ret;

    boot[0] = '\0';
    if (src.fd < 0)
        return -1;

    ret = psxBootName(src, boot, boot_max);
    if (ret == 0)
        ret = findPath(src, boot, &lba, &size);
    if (ret != 0 && boot_max >= (int)sizeof("PSX.EXE") && findPath(src, "PSX.EXE", &lba, &size) == 0) {
        strcpy(boot, "PSX.EXE");
        ret = 0;
    }
    close(src.fd);

    return ret;
}

int RaHash::hashVcd(const char *vcdpath, char *boot, int boot_max, char *out33)
{
    RaSrc src = {-1, RA_SRC_VCD, NULL};
    int ret;

    out33[0] = '\0';
    boot[0] = '\0';

    step("1-opening-vcd");
    src.fd = open(vcdpath, O_RDONLY);
    if (src.fd < 0) {
        step("1-open-failed");
        return -1;
    }

    ret = hashPsx(src, boot, boot_max, out33);
    close(src.fd);

    return ret;
}

/* PS1 image identity is the VCD path, not BOOT from SYSTEM.CNF. The latter
   can be shared by many distinct PS1 games (especially PSX.EXE homebrew).
   Retain the client's 15-byte serial ABI; derive a stable per-image key
   without rereading the VCD's executable each time a game launches.
   Including the mounted device root prevents two simultaneous USB volumes
   with identically named VCDs from sharing the in-memory watch list. */
int raVcdWatchKey(const char *vcdpath, char *out, int out_size)
{
    static const char hex[] = "0123456789abcdef";
    md5_state_t md5;
    md5_byte_t digest[16];
    const unsigned char *p;
    int i;

    if (vcdpath == NULL || !vcdpath[0] || out == NULL || out_size < 16)
        return -1;

    md5_init(&md5);
    for (p = (const unsigned char *)vcdpath; *p; p++) {
        unsigned char c = *p;
        if (c >= 'A' && c <= 'Z')
            c += 'a' - 'A';
        if (c == '\\')
            c = '/';
        md5_append(&md5, &c, 1);
    }
    md5_finish(&md5, digest);

    out[0] = 'P';
    for (i = 0; i < 7; i++) {
        out[i * 2 + 1] = hex[digest[i] >> 4];
        out[i * 2 + 2] = hex[digest[i] & 15];
    }
    out[15] = '\0';
    return 0;
}

/* A path-only session key identifies the VCD for the 15-byte wire format,
   but not its contents. Bind the persisted watch list to the precise RA hash
   that was checked with the PC. The guard is advisory, never a launch block. */
static int raVcdGuardPath(const char *root, const char *key, char *out, int size)
{
    int n, i;

    if (!root || !key || key[0] != 'P' || strlen(key) != 15 || !out || size < 1)
        return -1;
    for (i = 1; i < 15; i++)
        if (!isxdigit((unsigned char)key[i]) || isupper((unsigned char)key[i]))
            return -1;
    n = snprintf(out, size, "%sRA/%s.md5", root, key);
    return n >= 0 && n < size ? 0 : -1;
}

static int raVcdValidContentHash(const char *hash)
{
    int i;

    if (!hash || strlen(hash) != 32)
        return 0;
    for (i = 0; i < 32; i++)
        if (!isxdigit((unsigned char)hash[i]) || isupper((unsigned char)hash[i]))
            return 0;
    return 1;
}

int raVcdWatchGuardStore(const char *watchRoot, const char *watchKey, const char *hash)
{
    char path[256];
    FILE *f;
    size_t wrote;
    int closed;

    if (!raVcdValidContentHash(hash) || raVcdGuardPath(watchRoot, watchKey, path, sizeof(path)) != 0)
        return -1;
    f = fopen(path, "wb");
    if (!f)
        return -1;
    wrote = fwrite(hash, 1, 32, f);
    closed = fclose(f);
    if (wrote != 32 || closed != 0) {
        unlink(path); /* A partial guard must not authorize a stale list. */
        return -1;
    }
    return 0;
}

int raVcdWatchGuardMatches(const char *watchRoot, const char *watchKey, const char *hash)
{
    char path[256], recorded[33];
    FILE *f;
    size_t len;
    int extra;

    if (!raVcdValidContentHash(hash) || raVcdGuardPath(watchRoot, watchKey, path, sizeof(path)) != 0)
        return 0;
    f = fopen(path, "rb");
    if (!f)
        return 0;
    len = fread(recorded, 1, 32, f);
    extra = fgetc(f); /* Reject truncated/extended/corrupt guards. */
    fclose(f);
    return len == 32 && extra == EOF && memcmp(recorded, hash, 32) == 0;
}
