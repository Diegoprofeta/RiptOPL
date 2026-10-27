"""Exercise actual browse-prefetch generations and worker ownership under reentrant selection changes."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "src/ui/menusys.cpp").read_text(encoding="utf-8")

def function(signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]

methods = "\n".join(function(s) for s in (
    "static void _menuLoadConfigAsync()", "static void _menuRequestConfig()",
    "void menuInvalidateConfig()", "static void menuNextH()", "static void menuPrevH()",
))
program = r'''
#include <cassert>
#include <cstdio>
#include <vector>
struct config_set_t { int serial; };
struct item_list_t { int delay; } first{1}, second{1};
struct Row { struct { int id; } item; } row{{1}};
struct Item { void *userdata; Row *current; int visible=1; } item{&first,&row};
struct menu_list { Item *item; menu_list *next=nullptr, *prev=nullptr; };
using Menu=menu_list;
static Menu menu{&item};
static Menu *selected_item=&menu;
static config_set_t *itemConfig;
static item_list_t *itemConfigList;
static int itemConfigId=-1, menuSemaId, actionStatus, guiInactiveFrames=9, depth;
static unsigned char itemConfigWorkerPending;
static unsigned int itemConfigGeneration;
static int reads, frees, queues, scenario, waiterCalls, moves;
static bool failQueue, failRead;
static std::vector<void *> pending;
constexpr int IO_CUSTOM_SIMPLEACTION=1, IO_OK=0;
static void WaitSema(int) { assert(depth++==0); }
static void SignalSema(int) { assert(--depth==0); }
namespace raii { struct SemaLock { int id; SemaLock(int n):id(n) {WaitSema(id);} ~SemaLock(){SignalSema(id);} }; }
static void configFree(config_set_t *p) { assert(p); ++frees; delete p; }
static void _menuLoadConfig() { assert(!depth); ++waiterCalls; actionStatus=0; }
static void menuFolderResetLeaving(Menu *) { assert(depth==1); ++moves; }
constexpr int SFX_CURSOR=1;
static void sfxPlay(int sound) { assert(!depth && sound==SFX_CURSOR); } // audio RPCs run outside menuSemaId (#980)
static void _menuRequestConfig();
static void menuInvalidateConfig();
static int ioPutRequest(int type,void *fn) { assert(!depth && type==IO_CUSTOM_SIMPLEACTION); ++queues; if(failQueue)return -1; pending.push_back(fn); return IO_OK; }
struct Source { config_set_t *config(item_list_t *list,int id) {
    assert(!depth); ++reads;
    if (scenario && reads==1) {
        if (scenario==1) { row.item.id=2; _menuRequestConfig(); row.item.id=3; _menuRequestConfig(); }
        if (scenario==2) { item.userdata=&second; _menuRequestConfig(); item.userdata=&first; _menuRequestConfig(); }
        if (scenario==3) { menuInvalidateConfig(); _menuRequestConfig(); }
        if (scenario==4) { row.item.id=2; } // cursor moved but has not settled/requested yet
    }
    (void)list; (void)id;
    return failRead ? nullptr : new config_set_t{reads};
} } source;
static Source *gsOf(item_list_t *) { return &source; }
@METHODS@
static void reset() {
    assert(!depth && !itemConfigWorkerPending); if(itemConfig)configFree(itemConfig);
    itemConfig=nullptr; itemConfigList=nullptr; itemConfigId=-1; itemConfigGeneration=0;
    row.item.id=1; item.userdata=&first; item.current=&row; menu.item=&item; selected_item=&menu;
    actionStatus=0; guiInactiveFrames=9; reads=frees=queues=scenario=0; failQueue=failRead=false; pending.clear();
}
static void run() {
    assert(pending.size()==1);
    auto callback=reinterpret_cast<void (*)()>(pending.front());
    pending.clear(); callback();
    assert(!itemConfigWorkerPending && !depth);
}
int main() {
    reset(); _menuRequestConfig(); _menuRequestConfig(); assert(queues==1); run();
    assert(reads==1 && itemConfig && itemConfig->serial==1); _menuRequestConfig(); assert(queues==1);
    for(int n: {1,2,3}) {
        reset(); scenario=n; _menuRequestConfig(); run();
        assert(queues==1 && reads==2 && frees==1 && itemConfig && itemConfig->serial==2);
        assert(itemConfigList==&first && itemConfigId==(n==1?3:1));
    }
    reset(); scenario=4; _menuRequestConfig(); run(); assert(!itemConfig && frees==1);
    _menuRequestConfig(); run(); assert(itemConfig && itemConfigId==2 && reads==2);
    reset(); failQueue=true; _menuRequestConfig(); assert(!itemConfigWorkerPending && itemConfigId==-1);
    failQueue=false; _menuRequestConfig(); run(); assert(itemConfig && queues==2);
    reset(); failRead=true; _menuRequestConfig(); run(); assert(!itemConfig && !itemConfigWorkerPending);
    menuInvalidateConfig(); failRead=false; _menuRequestConfig(); run(); assert(itemConfig);
    reset(); _menuRequestConfig(); selected_item=nullptr; run(); assert(!reads && !itemConfig);
    reset(); _menuRequestConfig(); actionStatus=7; run(); assert(actionStatus==7); // browse worker cannot release a dialog waiter
    reset(); itemConfigList=&first; itemConfigId=0; guiInactiveFrames=0; _menuRequestConfig(); assert(!queues);
    reset(); actionStatus=1; _menuRequestConfig(); run();
    assert(waiterCalls==1 && !reads && !actionStatus);
    reset(); Item hiddenItem{&first,&row,0}, lastItem{&second,&row,1};
    Menu hidden{&hiddenItem}, last{&lastItem};
    menu.next=&hidden;hidden.prev=&menu;hidden.next=&last;last.prev=&hidden;
    auto generation=itemConfigGeneration;
    menuNextH(); assert(selected_item==&last && itemConfigId==-1 && itemConfigGeneration==generation+1 && moves==1);
    menuNextH(); assert(selected_item==&last && itemConfigGeneration==generation+1 && !depth);
    menuPrevH(); assert(selected_item==&menu && itemConfigGeneration==generation+2 && moves==2 && !depth);
    menu.next=nullptr;
    reset(); puts("PASS: one browse worker, latest target, ABA invalidation, refusal retry and waiter isolation");
}
'''.replace("@METHODS@", methods)
with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "prefetch.cpp"
    exe = Path(tmp) / "prefetch"
    src.write_text(program, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-pie", "-no-pie",
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
