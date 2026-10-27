/*
  ratls_ps2.cpp -- the console half of the RetroAchievements HTTPS lookup.

  Supplies what src/platform/ratls.c needs on a PS2: DNS and a TCP connection
  through the menu's network stack (ps2ips), a BIO that reads with lwIP's
  per-call non-blocking flag under an overall deadline (fcntl O_NONBLOCK has no
  effect on this stack, see ranet.cpp), the console clock as UTC, an entropy
  source, mbedtls_ms_time(), and the five embedded roots (third_party/ca-roots,
  turned into asm/ratls_root_<name>.c by tools/assets.py embed).

  Runs on the I/O worker. Refuses while a UDP transport owns the NIC.
*/

#include "include/ratls.h"
#include "include/ranet.h" /* raNetNicReserved, raNetTcpRecv */

#include <ps2ips.h>
#include <netinet/in.h> /* sockaddr_in */
#include <lwip/def.h>   /* htons */
#include <netdb.h>
#include <kernel.h>
#include <delaythread.h>
#include <libcdvd.h>
#include <string.h>
#include <time.h>

#include "mbedtls/net_sockets.h" /* MBEDTLS_ERR_NET_SEND_FAILED */
#include "mbedtls/platform_time.h"
#include "mbedtls/ssl.h"

/* <netdb.h> only declares struct hostent, and <tcpip.h>, which defines it, clashes with
   <netinet/in.h>. This is its layout there (lwIP's LWIP_DNS_API_DECLARE_STRUCTS). */
struct hostent
{
    char *h_name;
    char **h_aliases;
    int h_addrtype;
    int h_length;
    char **h_addr_list;
};

constexpr int RATLS_DEADLINE_MS = 8000; /* the same budget as the xeRAbora HTTP fetch (RA_HTTP_MS) */
constexpr int RATLS_POLL_MS = 25;
constexpr int RATLS_MIN_YEAR = 2025; /* an earlier RTC is unset: fail closed */

extern "C" {
extern unsigned char ratls_root_gtsr1[], ratls_root_gtsr3[], ratls_root_gtsr4[];
extern unsigned char ratls_root_isrgrootx1[], ratls_root_isrgrootx2[];
extern unsigned int size_ratls_root_gtsr1, size_ratls_root_gtsr3, size_ratls_root_gtsr4;
extern unsigned int size_ratls_root_isrgrootx1, size_ratls_root_isrgrootx2;
mbedtls_ms_time_t mbedtls_ms_time(void);
int mbedtls_hardware_poll(void *data, unsigned char *out, size_t len, size_t *olen);
}

static int bcd(unsigned char v)
{
    return (v >> 4) * 10 + (v & 0x0F);
}

static long long ratlsNow(void)
{
    sceCdCLOCK clk;

    if (sceCdReadClock(&clk) == 0)
        return -1;
    int year = 2000 + bcd(clk.year);
    if (year < RATLS_MIN_YEAR)
        return -1;
    return raTlsRtcToUtc(year, bcd(clk.month & 0x1F), bcd(clk.day), bcd(clk.hour), bcd(clk.minute), bcd(clk.second));
}

mbedtls_ms_time_t mbedtls_ms_time(void)
{
    return static_cast<mbedtls_ms_time_t>(clock()) * 1000 / CLOCKS_PER_SEC;
}

static inline unsigned int cop0Count(void)
{
    unsigned int count;
    __asm__ volatile("mfc0 %0, $9"
                     : "=r"(count));
    return count;
}

/* The PS2 has no hardware RNG. Each output byte folds 8 samples of the
   294.912 MHz COP0 count's low bits across a thread switch (interrupt and DMA
   timing make them jitter), credited at 1 bit per sample; the CDVD clock and
   clock() are mixed in once per call. mbedTLS's entropy accumulator gathers
   until the CTR_DRBG seed reaches its threshold (spec: >= 512 samples, about
   256 bits by this estimate). */
int mbedtls_hardware_poll(void *data, unsigned char *out, size_t len, size_t *olen)
{
    sceCdCLOCK clk;

    (void)data;
    for (size_t i = 0; i < len; i++) {
        unsigned char byte = 0;
        for (int s = 0; s < 8; s++) {
            unsigned int before = cop0Count();
            DelayThread(1);
            byte = static_cast<unsigned char>((byte << 1) | (byte >> 7)) ^ static_cast<unsigned char>(cop0Count() - before);
        }
        out[i] = byte ^ static_cast<unsigned char>(clock());
    }
    if (len >= sizeof(clk) && sceCdReadClock(&clk) != 0) {
        const unsigned char *c = reinterpret_cast<const unsigned char *>(&clk);
        for (size_t i = 0; i < sizeof(clk); i++)
            out[i] ^= c[i];
    }
    *olen = len;
    return 0;
}

struct RatlsBio
{
    int sock;
    clock_t start; /* the budget runs from before DNS */
};

/* clock() is a 32-bit microsecond counter here: compare elapsed time, which survives the wrap,
   and keep the product small (milliseconds times a full CLOCKS_PER_SEC would overflow). */
static int ratlsExpired(clock_t start)
{
    return (clock_t)(clock() - start) >= (clock_t)RATLS_DEADLINE_MS * (CLOCKS_PER_SEC / 1000);
}

static int bioSend(void *ctx, const unsigned char *buf, size_t len)
{
    RatlsBio *bio = static_cast<RatlsBio *>(ctx);
    int n = send(bio->sock, const_cast<unsigned char *>(buf), len, 0);
    return n < 0 ? MBEDTLS_ERR_NET_SEND_FAILED : n;
}

/* Reads through a 64-byte-aligned bounce buffer with raNetTcpRecv (whole 64-byte blocks, or at
   most 64 bytes, so ps2ips never drops a tail), polling until data, close or the deadline. */
static int bioRecv(void *ctx, unsigned char *buf, size_t len)
{
    static unsigned char chunk[960] __attribute__((aligned(64)));
    RatlsBio *bio = static_cast<RatlsBio *>(ctx);

    for (;;) {
        if (ratlsExpired(bio->start))
            return MBEDTLS_ERR_SSL_TIMEOUT;
        int got = raNetTcpRecv(bio->sock, chunk, len < sizeof(chunk) ? static_cast<int>(len) : static_cast<int>(sizeof(chunk)));
        if (got == 0)
            return 0; /* closed */
        if (got > 0) {
            memcpy(buf, chunk, got);
            return got;
        }
        DelayThread(RATLS_POLL_MS * 1000);
    }
}

int raHttpsGet(const char *host, const char *path, char *buf, int max, int *length)
{
    const ratls_anchor_t anchors[] = {
        {ratls_root_gtsr1, size_ratls_root_gtsr1},
        {ratls_root_gtsr3, size_ratls_root_gtsr3},
        {ratls_root_gtsr4, size_ratls_root_gtsr4},
        {ratls_root_isrgrootx1, size_ratls_root_isrgrootx1},
        {ratls_root_isrgrootx2, size_ratls_root_isrgrootx2},
    };
    struct sockaddr_in to;
    clock_t start = clock();

    if (length != NULL)
        *length = 0;
    if (!raTlsClockOk(ratlsNow)) /* before any DNS lookup or connection */
        return RATLS_ERR_CLOCK;
    if (raNetNicReserved())
        return RATLS_ERR_NET;

    struct hostent *he = gethostbyname(host);
    if (he == NULL || he->h_addr_list == NULL || he->h_addr_list[0] == NULL)
        return RATLS_ERR_NET;
    memset(&to, 0, sizeof(to));
    to.sin_family = AF_INET;
    to.sin_port = htons(443);
    memcpy(&to.sin_addr, he->h_addr_list[0], sizeof(to.sin_addr));

    RatlsBio bio = {socket(AF_INET, SOCK_STREAM, 0), start};
    if (bio.sock < 0)
        return RATLS_ERR_NET;
    if (connect(bio.sock, reinterpret_cast<struct sockaddr *>(&to), sizeof(to)) < 0) {
        disconnect(bio.sock);
        return RATLS_ERR_NET;
    }
    if (ratlsExpired(start)) { /* DNS and connect already used the budget */
        disconnect(bio.sock);
        return RATLS_ERR_TIMEOUT;
    }
    const ratls_io_t io = {bioSend, bioRecv, &bio, ratlsNow};

    int rc = raTlsRequest(&io, host, path, "RiptOPL/" OPL_VERSION, anchors, sizeof(anchors) / sizeof(anchors[0]), buf, max, length);
    disconnect(bio.sock);
    return rc;
}
