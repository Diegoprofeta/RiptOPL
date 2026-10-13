"""Execute Favorites reader/edit/writer bodies with IO and allocation faults."""
from pathlib import Path
import os
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "src/sources/favsupport.cpp").read_text(encoding="utf-8")
# Permit reproducing the same edit regression against the original C bodies.
source = source.replace("int addFavouriteItem(", "int FavSupport::addItem(")
source = source.replace("int removeFavouriteByIdAndText(", "int FavSupport::removeByIdAndText(")


def function(signature):
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]


def run(name, body):
    parent = ROOT / "build/test-tmp"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as tmp:
        cpp, exe = Path(tmp) / (name + ".cpp"), Path(tmp) / name
        cpp.write_text(body, encoding="utf-8")
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        subprocess.run([*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        "-no-pie", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=15)


prefix = r'''
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <algorithm>
#include <fcntl.h>
using u8 = unsigned char;
using u16 = unsigned short;
using u32 = unsigned int;
constexpr int FAV_MAX_ITEMS=512, FAV_TEXT_MAX=256, FAV_VERSION=3;
constexpr u32 FAV_MAGIC=0x4641464f;
enum {ETH_MODE=8,HDD_MODE=9,APP_MODE=10,FAV_MODE=12,MMCE_MODE=11,
      FAV_KIND_ISO=0,FAV_KIND_VCD=1,FAV_KIND_ELF=3};
struct fav_raw_t {int mode,id,icon_id,text_id,kind; char text[FAV_TEXT_MAX];};
#define LOG(...) ((void)0)
'''

# These use the actual editing methods, while a failed/partial read is injected at
# their storage boundary. Old methods overwrite the store before this assertion.
run("favorites_failed_read_edit", prefix + r'''
static int complete, rawCount, writes;
static fav_raw_t *favReadFile(int *count, int *editable=nullptr) {
    *count=rawCount; if(editable) *editable=complete;
    if(!rawCount) return nullptr;
    auto *p=static_cast<fav_raw_t*>(calloc(rawCount,sizeof(fav_raw_t)));
    assert(p); p[0].mode=3; p[0].id=7; strcpy(p[0].text,"previous"); return p;
}
static int favWriteFile(fav_raw_t*,int) {++writes;return 1;}
static int favModesMatch(int a,int b){return a==b;}
static int favIdsMatchForMode(int,int a,int b){return a==b;}
class FavSupport { public:
 int addItem(int,int,int,int,const char*,int);
 int removeByIdAndText(int,int,const char*,int);
};
''' + function("int FavSupport::addItem(") + function("int FavSupport::removeByIdAndText(") + r'''
int main() {
 FavSupport store;
 // Missing and valid-empty are editable; IO/allocation/corruption failures are not.
 complete=0; rawCount=0;
 assert(!store.addItem(3,8,0,0,"new",0) && writes==0);
 rawCount=1;
 assert(!store.addItem(3,8,0,0,"new",0) && writes==0);
 assert(!store.removeByIdAndText(3,7,"previous",0) && writes==0);
 complete=1; rawCount=0;
 assert(store.addItem(3,8,0,0,"new",0) && writes==1);
 rawCount=1;
 assert(store.addItem(3,7,0,0,"previous",0) && writes==1);
 assert(store.removeByIdAndText(3,7,"previous",0) && writes==2);
}
''')

io = r'''
static std::vector<u8> disk;
static int position, readLimit=1000000, writeLimit=1000000, failReadAt=-1;
static int openError, closeError, writeErrorAt=-1, writeZeroAt=-1, opens, closes, writes;
static bool failSeek, failAllocation;
static int fakeOpen(const char*,int flags,...) {
 ++opens; if(openError) {errno=openError;return -1;} position=0;
 if(flags&O_TRUNC) disk.clear();
 return 17;
}
static int fakeRead(int fd,void *out,int size) {
 assert(fd==17);
 if(failReadAt>=0 && position>=failReadAt) {errno=EIO; return -1;}
 int n=std::min({size,readLimit,static_cast<int>(disk.size())-position});
 if(failReadAt>=0) n=std::min(n,failReadAt-position);
 if(n) memcpy(out,disk.data()+position,n);
 position+=n; return n;
}
static int fakeWrite(int fd,const void *in,int size) {
 assert(fd==17); ++writes;
 if(writeErrorAt>=0 && position>=writeErrorAt) {errno=EIO;return -1;}
 if(writeZeroAt>=0 && position>=writeZeroAt) return 0;
 int n=std::min(size,writeLimit);
 if(writeErrorAt>=0) n=std::min(n,writeErrorAt-position);
 if(writeZeroAt>=0) n=std::min(n,writeZeroAt-position);
 const auto *p=static_cast<const u8*>(in); disk.insert(disk.end(),p,p+n);position+=n; return n;
}
static int fakeClose(int fd) {assert(fd==17);++closes;return closeError?-1:0;}
static int fakeSeek(int fd,int pos,int) {assert(fd==17);if(failSeek)return -1;position=pos;return pos;}
static void *fakeMalloc(size_t n) {return failAllocation?nullptr:malloc(n);}
static void *fakeCalloc(size_t n,size_t s) {return failAllocation?nullptr:calloc(n,s);}
static void favGetFilePath(char *p,int) {strcpy(p,"mc0:OPL/favourites.bin");}
static void reset() {
 position=0;readLimit=writeLimit=1000000;failReadAt=writeErrorAt=writeZeroAt=-1;
 openError=closeError=opens=closes=writes=0;failSeek=failAllocation=false;
}
#define open fakeOpen
#define read fakeRead
#define write fakeWrite
#define close fakeClose
#define lseek fakeSeek
#define malloc fakeMalloc
#define calloc fakeCalloc
'''
reader_start = "static int rdFull(" if "static int rdFull(" in source else "static int rdBytes("
reader = source[source.index(reader_start):source.index("// Little-endian scalar appenders")]
writer = source[source.index("static void bufU16("):source.index("// ---- resolution helpers")]

# The old reader is wrapped with its previous implicit editable assumption so the
# regression fails at runtime rather than simply failing to compile its old API.
load = "return favReadFile(n,editable);" if "int *editable" in function("static fav_raw_t *favReadFile(") else "*editable=1;return favReadFile(n);"
run("favorites_storage_io", prefix + io + reader + writer + r'''
static fav_raw_t *load(int *n,int *editable) {''' + load + r'''}
static void expect(int count,int editable) {
 int n=-1,e=-1; auto *r=load(&n,&e); assert(n==count && e==editable);
 if(count) assert(r);
 free(r); assert(closes==opens);
}
int main() {
 fav_raw_t row{};row.mode=APP_MODE;row.id=3;strcpy(row.text,"test");
 reset(); assert(favWriteFile(&row,1)); const auto valid=disk;
 reset(); assert(!favWriteFile(nullptr,1) && !favWriteFile(&row,-1) &&
                 !favWriteFile(&row,FAV_MAX_ITEMS+1) && opens==0);
 reset(); expect(1,1);
 // Scalar/text reads and writes accumulate valid positive short transfers.
 reset();readLimit=1;expect(1,1);
 reset();writeLimit=2;assert(favWriteFile(&row,1) && disk==valid && writes>1);
 reset();closeError=1;assert(!favWriteFile(&row,1) && closes==1);
 reset();writeErrorAt=4;assert(!favWriteFile(&row,1) && closes==1);
 reset();writeZeroAt=4;assert(!favWriteFile(&row,1) && closes==1);
 reset();failAllocation=true;assert(!favWriteFile(&row,1) && opens==0);
 reset();openError=EACCES;assert(!favWriteFile(&row,1) && closes==0);
 disk=valid;reset();failReadAt=4;expect(0,0);
 disk=valid;reset();failAllocation=true;expect(0,0);
 disk=valid;reset();closeError=1;expect(1,0);
 disk=valid;reset();disk[4]=FAV_VERSION+1;expect(0,0);
 disk=valid;reset();disk[4]=0;expect(0,0);
 disk=valid;disk[4]=2;reset();expect(1,1);
 disk=valid;disk[4]=1;disk.erase(disk.begin()+22);reset();expect(1,1);
 // A salvaged prefix may still display, but must never become a replacement list.
 disk=valid;disk[6]=2;reset();expect(1,0);
 disk=valid;disk.back()='x';reset();expect(1,0);
 disk=valid;disk.push_back(1);reset();expect(1,0);
 // A genuinely empty OFAV store is editable, unlike a zero-byte/torn header.
 reset();assert(favWriteFile(nullptr,0));reset();expect(0,1);
 disk.clear();reset();expect(0,0);
 disk={1,2,3};reset();expect(0,0);
 // ENOENT alone permits a new store; unknown, permission and device errors refuse.
 for(int e:{EIO,EACCES,EPERM,EMFILE}) {
   reset();openError=e;int n,eout;auto*r=load(&n,&eout);assert(!r && !n && !eout && !closes);
 }
 reset();openError=ENOENT;int n,eout;auto*r=load(&n,&eout);assert(!r && !n && eout && !closes);
 // Legacy import is editable only after complete records and clean EOF/close.
 std::vector<u8> foreign(32,0);foreign[0]=5;foreign[12]=7;
 foreign.insert(foreign.end(),{5,0,0,0,'t','e','s','t',0,5,0});
 disk=foreign;reset();readLimit=2;expect(1,1);
 disk=foreign;disk.push_back(9);reset();expect(1,0);
 disk=foreign;reset();failSeek=true;expect(0,0);
 disk=foreign;reset();closeError=1;expect(1,0);
 disk=foreign;disk[disk.size()-3]='x';reset();expect(1,0);
 disk.clear();for(int i=0;i<FAV_MAX_ITEMS;i++)disk.insert(disk.end(),foreign.begin(),foreign.end());
 reset();expect(FAV_MAX_ITEMS,1);
 disk.insert(disk.end(),foreign.begin(),foreign.end());reset();expect(FAV_MAX_ITEMS,0);
 // Reject editing oversized lists rather than silently saving just the first 512.
 reset();std::vector<fav_raw_t> many(FAV_MAX_ITEMS,row);assert(favWriteFile(many.data(),many.size()));
 reset();disk[6]=1;disk[7]=2;expect(FAV_MAX_ITEMS,0);
}
''')
print("Favorites failed-read editing and real reader/writer IO fault regressions passed")
