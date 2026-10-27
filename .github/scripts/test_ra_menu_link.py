"""Run the production menu-side RA client (src/sources/ranet.cpp) against a scripted network.

Ported from the original's test_ra_verified_peer, test_ra_mstack_link, test_ra_caduceus_host,
test_ra_nic_reserved and test_ra_udpfs_check, merged into one harness that drives the public
methods end to end: every request, its destination and every reply source are observed.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "src/sources/ranet.cpp").read_text(encoding="utf-8")
# Everything after the includes is production code; the harness supplies what they declared.
body = source[source.index("\n", source.index("#include <fileXio_rpc.h>")):source.rindex("#endif")]

harness = r'''
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <fcntl.h>
#include "include/ranet.h"
#include "modules/network/common/ra_client.h"
typedef uint8_t u8;
typedef uint32_t u32;
#define LOG(...) ((void)0)
enum { NET_PROTO_OFF, NET_PROTO_SMB, NET_PROTO_UDPFS, NET_PROTO_UDPFSBD, NET_PROTO_UDPBD };
enum { RA_MODE_XERABORA, RA_MODE_CADUCEUS };
enum { _STR_RA_SUPPORTED, _STR_RA_ACHIEVEMENTS_FULL, _STR_RA_ACHIEVEMENTS, _STR_RA_WL_NOT_SAVED,
       _STR_RA_NO_LINK_UNTRACKED, _STR_CAD_UNTRACKED, _STR_RA_NET_BUSY, _STR_RA_UDPFS_LOAD_FIRST,
       _STR_RA_NET_BUSY2, _STR_RA_NO_SOCKET, _STR_RA_NO_SOCKET2, _STR_RA_NO_IP, _STR_RA_NO_IP2,
       _STR_RA_CADUCEUS_OFFLINE, _STR_RA_TEST_NO_ANSWER, _STR_RA_CADUCEUS_SIGN_IN,
       _STR_RA_TEST_NO_ANSWER2, _STR_RA_TEST_FOUND, _STR_RA_TEST_FOUND2 };
static const char *_l(int id)
{
    static const char *text[] = {"supported", "%d %d %d", "%d achievements", "NOT SAVED", "no link",
                                 "cad untracked", "busy", "LOAD FIRST", "busy2", "nosock", "nosock2",
                                 "noip", "noip2", "OFFLINE", "no answer", "SIGN IN", "Console%s.",
                                 "found%s%s %s", "%u ms%s"};
    return text[id];
}
static int gNetworkProtocol, gRAMode, gRATelemetry = 1, ps2_ip_use_dhcp;
static int gRAHostIp[4], pc_ip[4], ps2_ip[4] = {192, 168, 1, 10};
static int udpbdLoaded, udpfsLoaded, ethInits, warnings, lastWarning = -1, watchCount, cleared;
static int bdmIsUDPBDLoaded() { return udpbdLoaded; }
static int udpfsGetModulesLoaded() { return udpfsLoaded; }
static void raHashStep(const char *) {}
static void DelayThread(int) {}
static int ethLoadInitModules() { ethInits++; return 0; }
static int ethGetNetConfig(u8 *ip, u8 *, u8 *) { for (int i = 0; i < 4; i++) ip[i] = ps2_ip[i]; return 0; }
static int ethGetDHCPStatus() { return 1; }
#define NETMAN_NETIF_IOCTL_GET_LINK_STATUS 1
#define NETMAN_NETIF_ETH_LINK_STATE_UP 1
static int linkState = 1;
static int NetManIoctl(int, void *, int, void *, int) { return linkState; }
static int GetWatchCount() { return watchCount; }
static void ClearWatchList() { cleared++; watchCount = 0; }
static int parsedBytes;
static int SetWatchList(const void *, int bytes, const char *) { parsedBytes = bytes; watchCount = 1; return 1; }
struct Ui { void warning(const char *text, int) { warnings++; lastWarning = !strcmp(text, "cad untracked"); } };
namespace host { static Ui ui() { return Ui(); } }

/* The network: each request is answered by respond(), queued for the next receive. */
struct Packet { u32 ip; int port; std::string text; };
static std::vector<Packet> sent, pending;
static std::vector<Packet> (*respond)(const Packet &);
static int sockets, closed, bindFails;
static int fake_socket(int, int, int) { return ++sockets; }
static int disconnect(int) { closed++; return 0; }
static int fake_bind(int, const sockaddr *, socklen_t) { return bindFails ? -1 : 0; }
static int fake_setsockopt(int, int, int, const void *, socklen_t) { return 0; }
static int fake_fcntl(int, int, ...) { return 0; }
static void deliver(const Packet &request)
{
    sent.push_back(request);
    if (respond)
        for (const Packet &reply : respond(request))
            pending.push_back(reply);
}
static ssize_t fake_sendto(int, const void *data, size_t len, int, const sockaddr *to, socklen_t)
{
    const sockaddr_in *in = (const sockaddr_in *)to;
    deliver({in->sin_addr.s_addr, ntohs(in->sin_port), std::string((const char *)data, len)});
    return len;
}
static ssize_t fake_recvfrom(int, void *buf, size_t max, int, sockaddr *from, socklen_t *)
{
    if (pending.empty())
        return -1;
    Packet p = pending.front();
    pending.erase(pending.begin());
    size_t n = p.text.size() < max ? p.text.size() : max;
    memcpy(buf, p.text.data(), n);
    ((sockaddr_in *)from)->sin_addr.s_addr = p.ip;
    return n;
}
#define socket fake_socket
#define bind fake_bind
#define setsockopt fake_setsockopt
#define fcntl fake_fcntl
#define sendto fake_sendto
#define recvfrom fake_recvfrom

/* mstack: the UDPFS chain's exchange device. */
static int mstackVersion = -19, mstackGetIp = 4, devctls;
static int fileXioDevctl(const char *, int cmd, void *arg, unsigned int, void *buf, unsigned int)
{
    devctls++;
    if (cmd == MSTACK_DEVCTL_VERSION)
        return mstackVersion;
    if (cmd == MSTACK_DEVCTL_GET_IP) {
        u8 own[4] = {10, 0, 0, 9};
        if (mstackGetIp == 4)
            memcpy(buf, own, 4);
        return mstackGetIp;
    }
    const mstack_xchg_req_t *req = (const mstack_xchg_req_t *)arg;
    deliver({req->dst_ip, req->dst_port, std::string((const char *)req->data, req->len)});
    if (pending.empty())
        return -116;
    Packet p = pending.front();
    pending.erase(pending.begin());
    mstack_xchg_reply_t *reply = (mstack_xchg_reply_t *)buf;
    reply->src_ip = p.ip;
    memcpy(reply->data, p.text.data(), p.text.size());
    return p.text.size();
}

/* Files. */
static int opens, written, unlinked, writeShort;
static int mkdir(const char *, int) { return 0; }
static FILE *fake_fopen(const char *, const char *) { opens++; return (FILE *)1; }
static size_t fake_fwrite(const void *, size_t size, size_t count, FILE *) { written++; return writeShort ? 0 : size * count; }
static int fake_fclose(FILE *) { return 0; }
static int unlink(const char *) { unlinked++; return 0; }
#define fopen fake_fopen
#define fwrite fake_fwrite
#define fclose fake_fclose
'''

tests = r'''
static u32 ip(int a, int b, int c, int d) { return (u32)a | (u32)b << 8 | (u32)c << 16 | (u32)d << 24; }
static const u32 PC = ip(192, 168, 1, 20), STRANGER = ip(192, 168, 1, 99), BCAST = 0xFFFFFFFFu;
static u32 serverIp = PC;
static std::string ready = "CADR2 " RA_PROBE_HASH " READY UNKNOWN";

/* A xeRAbora PC that knows one game with a one-byte list. A stranger answers a unicast first:
   a broadcast takes whoever answers, a unicast only its own host. */
static std::vector<Packet> xerabora(const Packet &r)
{
    std::vector<Packet> out;
    if (r.ip != 0xFFFFFFFFu)
        out.push_back({STRANGER, 0, "RAA1 NO stray"});
    if (r.text.rfind("CADQ2 ", 0) == 0)
        return {{serverIp, 0, std::string("CADR2 ") + r.text.substr(6) + " READY OK 1"}};
    if (r.text.rfind("RAQ1 ", 0) == 0)
        out.push_back({serverIp, 0, "RAA1 OK 1 1 3 2 0 Game"});
    else if (r.text.rfind("RAG1 ", 0) == 0)
        out.push_back({serverIp, 0, "RAC1 0 1 x"});
    else if (r.text.rfind("RAP1", 0) == 0)
        out.push_back({serverIp, 0, "RAO1 OK xeRAbora/1"});
    return out;
}
static std::vector<Packet> offline(const Packet &r)
{
    return {{serverIp, 0, std::string("CADR2 ") + r.text.substr(6) + " OFFLINE OK 1"}};
}
static int waits;
static std::vector<Packet> waiting(const Packet &r)
{
    if (r.text.rfind("RAQ1 ", 0) == 0 && waits-- > 0)
        return {{serverIp, 0, "RAA1 WAIT"}};
    return xerabora(r);
}
static std::vector<Packet> refusing(const Packet &) { return {{serverIp, 0, "RAA1 NO Set too big "}}; }

static Ranet client;
static char info[64], info2[64];
static void reset()
{
    sent.clear(); pending.clear(); respond = xerabora; serverIp = PC;
    gRAMode = RA_MODE_XERABORA; memset(gRAHostIp, 0, sizeof(gRAHostIp));
    pc_ip[0] = 192; pc_ip[1] = 168; pc_ip[2] = 1; pc_ip[3] = 20;
    gNetworkProtocol = NET_PROTO_SMB; udpbdLoaded = udpfsLoaded = 0; mstackVersion = -19; mstackGetIp = 4;
    sockets = closed = bindFails = ethInits = devctls = opens = written = unlinked = writeShort = 0;
    warnings = cleared = 0; lastWarning = -1; watchCount = 0; linkState = 1;
}
static int check() { return client.askPc("0123456789abcdef0123456789abcdef", "SLUS_123.45", "mass0:", info, sizeof(info), info2, sizeof(info2)); }

int main()
{
    /* Xerabora: broadcast discovery, the list from the PC that answered, a verified peer. */
    reset();
    assert(check() == 0 && parsedBytes == 1 && opens == 2 && closed == 1);
    assert(sent[0].ip == BCAST && sent[0].port == 18194 && !strcmp(info, "Game"));
    assert(client.peerIP() == PC);
    /* The peer is bound to the RA mode, the SMB host and the companion IP it was verified under. */
    gRAMode = RA_MODE_CADUCEUS; assert(client.peerIP() == 0); gRAMode = RA_MODE_XERABORA;
    for (int i = 0; i < 4; i++) { pc_ip[i]++; assert(client.peerIP() == 0); pc_ip[i]--; }
    gRAHostIp[3] = 7; assert(client.peerIP() == 0); gRAHostIp[3] = 0;
    assert(client.peerIP() == PC);
    /* A new check forgets it first, so a failed one leaves none. */
    respond = nullptr; assert(check() == -2 && client.peerIP() == 0);

    /* An explicit companion IP is unicast, and a reply from anywhere else is ignored. */
    reset(); serverIp = ip(10, 0, 0, 7);
    gRAHostIp[0] = 10; gRAHostIp[3] = 7;
    assert(check() == 0 && client.peerIP() == serverIp);
    for (const Packet &p : sent) assert(p.ip == serverIp && p.port == 18194);

    /* Caduceus: the session bridge on the SMB host first, then that PC's engine. */
    reset(); gRAMode = RA_MODE_CADUCEUS;
    assert(check() == 0 && sent[0].ip == PC && sent[0].port == RA_CADUCEUS_PORT);
    assert(sent[0].text == "CADQ2 0123456789abcdef0123456789abcdef");
    assert(sent[1].ip == PC && sent[1].port == 18194 && sent[1].text.rfind("RAQ1 ", 0) == 0);
    reset(); gRAMode = RA_MODE_CADUCEUS; respond = offline;
    assert(check() == -9 && parsedBytes == 1 && sent.size() == 1);
    reset(); gRAMode = RA_MODE_CADUCEUS; memset(pc_ip, 0, sizeof(pc_ip));
    assert(check() == -2 && sent.empty()); /* no host: never a broadcast to an arbitrary PC */
    memset(pc_ip, 255, sizeof(pc_ip));
    assert(check() == -2 && sent.empty());
    reset(); gRAMode = RA_MODE_CADUCEUS; gRAHostIp[0] = 10; gRAHostIp[3] = 7; serverIp = ip(10, 0, 0, 7);
    assert(check() == 0 && sent[0].ip == serverIp && sent[0].port == RA_CADUCEUS_PORT);

    /* A reserved NIC: refused without a socket or a network bring-up, unless mstack: is there. */
    for (int protocol : {NET_PROTO_UDPFS, NET_PROTO_UDPFSBD, NET_PROTO_UDPBD}) {
        reset(); gNetworkProtocol = protocol;
        assert(check() == -8 && sockets == 0 && ethInits == 0 && sent.empty());
    }
    reset(); udpbdLoaded = 1; assert(check() == -8 && sockets == 0);
    reset(); gNetworkProtocol = NET_PROTO_UDPFS; udpfsLoaded = 1; mstackVersion = MSTACK_XCHG_VERSION;
    assert(check() == 0 && sockets == 0 && closed == 0 && ethInits == 0);
    /* The PC replies to the address the ministack really owns, not a since-edited setting. */
    assert(sent[0].text.find(" 10.0.0.9 18196") != std::string::npos);
    reset(); gNetworkProtocol = NET_PROTO_UDPFS; udpfsLoaded = 1; mstackVersion = MSTACK_XCHG_VERSION;
    gRAHostIp[0] = 10; gRAHostIp[3] = 7; serverIp = ip(10, 0, 0, 7); /* mstack: filters the source too */
    assert(check() == 0 && client.peerIP() == serverIp && sent.size() > 2 && sent[1].ip == serverIp);
    reset(); gNetworkProtocol = NET_PROTO_UDPFS; udpfsLoaded = 1; mstackVersion = MSTACK_XCHG_VERSION; mstackGetIp = -22;
    assert(check() == 0 && sent[0].text.find(" 192.168.1.10 18196") != std::string::npos);

    /* WAIT keeps asking for up to 20 rounds; still waiting after that is -7. */
    reset(); respond = waiting; waits = 20; assert(check() == 0);
    reset(); respond = waiting; waits = 21; assert(check() == -7);
    /* "RAA1 NO <reason>" shows the PC's reason. */
    reset(); respond = refusing; assert(check() == 1 && !strcmp(info, "Set too big"));
    /* A failed bind is no link: replies must reach the fixed port. */
    reset(); bindFails = 1; assert(check() == -1 && closed == 1 && sent.empty());
    /* A short write is removed and reported; the PC still confirmed the game. */
    reset(); writeShort = 1;
    assert(check() == 0 && unlinked == 2 && !strcmp(info2, "NOT SAVED"));

    /* Launch: a busy NIC or a Caduceus session that is not ready drops the telemetry. */
    reset(); watchCount = 1; udpfsLoaded = 1; client.launchNetworkUp();
    assert(cleared == 1 && sent.empty());
    reset(); watchCount = 1; gRAMode = RA_MODE_CADUCEUS; respond = offline; client.launchNetworkUp();
    assert(cleared == 1 && lastWarning == 1 && client.peerIP() == 0);
    reset(); watchCount = 1; gRAMode = RA_MODE_CADUCEUS; client.launchNetworkUp();
    assert(cleared == 0 && warnings == 0 && client.peerIP() == PC && sent[0].port == RA_CADUCEUS_PORT);
    reset(); watchCount = 1; linkState = 0; client.launchNetworkUp();
    assert(cleared == 1 && lastWarning == 0);
    reset(); watchCount = 1; client.launchNetworkUp(); /* Xerabora sends nothing at launch */
    assert(cleared == 0 && sent.empty());

    /* Link test. */
    char one[64], two[64];
    reset(); assert(client.netTestLink(one, sizeof(one), two, sizeof(two)) == 1);
    assert(!strcmp(one, "found at 192.168.1.20 xeRAbora/1") && client.peerIP() == PC);
    reset(); respond = nullptr; assert(client.netTestLink(one, sizeof(one), two, sizeof(two)) == 0);
    assert(!strcmp(two, "Console 192.168.1.10 18196.") && client.peerIP() == 0);
    reset(); gRAHostIp[0] = gRAHostIp[1] = gRAHostIp[2] = gRAHostIp[3] = 255;
    assert(client.netTestLink(one, sizeof(one), two, sizeof(two)) == 0 && sent.empty());
    assert(!strcmp(two, "Console 192.168.1.10 18196.")); /* the console address, never a literal %s */
    reset(); gRAMode = RA_MODE_CADUCEUS; respond = offline;
    assert(client.netTestLink(one, sizeof(one), two, sizeof(two)) == 0 && !strcmp(one, "OFFLINE") && !strcmp(two, "SIGN IN"));
    reset(); respond = [](const Packet &) { return std::vector<Packet>{{PC, 0, "RAO1 FAIL"}}; };
    assert(client.netTestLink(one, sizeof(one), two, sizeof(two)) == 0 && client.peerIP() == 0);
    reset(); gNetworkProtocol = NET_PROTO_UDPFS;
    assert(client.netTestLink(one, sizeof(one), two, sizeof(two)) == 0 && !strcmp(two, "LOAD FIRST"));
    reset(); gNetworkProtocol = NET_PROTO_UDPBD;
    assert(client.netTestLink(one, sizeof(one), two, sizeof(two)) == 0 && !strcmp(two, "busy2"));
    puts("PASS: RA menu link: verified peers, explicit host, Caduceus session, mstack:, NIC reservation, launch and link test");
    return 0;
}
'''

compiler = shlex.split(os.environ.get("CXX", "c++"))
with tempfile.TemporaryDirectory() as directory:
    cpp, exe = Path(directory) / "link.cpp", Path(directory) / "link"
    cpp.write_text(harness + body + tests, encoding="utf-8")
    subprocess.run([*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined", "-I", str(ROOT),
                    str(cpp), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=60)

# Every caller tells a UDPFS chain that is not loaded yet apart from a busy NIC, and names an offline session.
for name in ("src/sources/supportbase.cpp", "src/sources/discsupport.cpp"):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "raNetUdpfsNotLoaded() ? _STR_RA_UDPFS_LOAD_FIRST : _STR_RA_NET_BUSY_HASH" in text, name
    assert "_STR_RA_CADUCEUS_OFFLINE" in text, name
# Applying network settings forgets the verified peer.
assert "raNetForgetPeer();" in (ROOT / "src/ui/guisettings.cpp").read_text(encoding="utf-8")
# The device registers only once the module stays resident.
main_c = (ROOT / "modules/network/udpfs_ministack/src/main.c").read_text(encoding="utf-8")
assert main_c.index("mstack_xchg_init();") > main_c.index("RegisterLibraryEntries(&_exp_mstack)")
include = source.index("#include <fileXio_rpc.h>")
assert "#define NEWLIB_PORT_AWARE" in source[:include], "fileXio_rpc.h included without NEWLIB_PORT_AWARE"
