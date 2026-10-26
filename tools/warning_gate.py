#!/usr/bin/env python3
"""Warning baseline for the ps2build main flavour.

    ps2build build 2>&1 | tee build.log       (clean build: warnings only print when compiling)
    tools/warning_gate.py build.log               summary by warning flag and by file
    tools/warning_gate.py build.log --check       fail if any (file, flag) count exceeds the baseline
    tools/warning_gate.py build.log --update      rewrite tools/warnings_baseline.json

Only warnings in this repository's own code are counted (src/, ee_core/, elfldr/, modules/, include/);
SDK headers, the downloaded lwNBD tree and the pinned mmceman tree are ignored. Counts are per
(file, flag), so refactors that move code between files show up, but unrelated edits do not.
"""
import collections, json, ntpath, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "tools", "warnings_baseline.json")
OWN = ("src/", "ee_core/", "elfldr/", "modules/", "include/")
SKIP = ("modules/network/lwNBD/", "modules/mmce/mmceman/")

rx = re.compile(r"^(.+?):\d+:\d+: warning: .*\[(-W[\w+-]+)\]\s*$")
rx_plain = re.compile(r"^(.+?):\d+:\d+: warning: (.*)$")


def log_lines(path):
    # Windows PowerShell's redirection writes UTF-16; native redirects and tee
    # normally write UTF-8. Both must feed the same warning ratchet.
    with open(path, "rb") as stream:
        bom = stream.read(2)
    encoding = "utf-16" if bom in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    with open(path, encoding=encoding, errors="replace") as stream:
        yield from stream

def parse(path):
    counts = collections.Counter()
    seen = set()
    for line in log_lines(path):
        line = line.rstrip("\n")
        m = rx.match(line)
        flag = None
        if m: f, flag = m.groups()
        else:
            m = rx_plain.match(line)
            if not m: continue
            f, msg = m.groups(); flag = "(" + re.sub(r"[‘’'].*", "", msg).strip()[:40] + ")"
        paths = ntpath if ntpath.splitdrive(f)[0] else os.path
        try:
            rel = paths.relpath(f, ROOT).replace("\\", "/")
        except ValueError:  # A diagnostic from another Windows drive is not ours.
            continue
        if not rel.startswith(OWN) or rel.startswith(SKIP): continue
        # the same header warning repeats once per including TU: count it once per (file, line text)
        key = (rel, flag, line)
        if key in seen: continue
        seen.add(key)
        counts[f"{rel}|{flag}"] += 1
    return counts

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args: sys.exit(__doc__)
    counts = parse(args[0])
    byflag = collections.Counter(); byfile = collections.Counter()
    for k, n in counts.items():
        f, flag = k.split("|"); byflag[flag] += n; byfile[f] += n
    if "--update" in sys.argv:
        json.dump(dict(sorted(counts.items())), open(BASELINE, "w"), indent=0, sort_keys=True); open(BASELINE, "a").write("\n")
        print(f"baseline written: {sum(counts.values())} warnings in {len(byfile)} files")
        return
    if "--check" in sys.argv:
        base = json.load(open(BASELINE))
        worse = {k: (base.get(k, 0), n) for k, n in counts.items() if n > base.get(k, 0)}
        better = sum(base.get(k, 0) - counts.get(k, 0) for k in base if counts.get(k, 0) < base[k])
        for k, (b, n) in sorted(worse.items()): print(f"NEW  {k}: {b} -> {n}")
        print(f"{sum(counts.values())} warnings (baseline {sum(base.values())}); {len(worse)} regressions, {better} fixed")
        sys.exit(1 if worse else 0)
    print(f"{sum(counts.values())} warnings in {len(byfile)} files")
    for flag, n in byflag.most_common(): print(f"  {n:4d} {flag}")
    print("top files:")
    for f, n in byfile.most_common(12): print(f"  {n:4d} {f}")

if __name__ == "__main__":
    main()
