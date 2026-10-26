"""Tab moves publish under the menu lock and play the cursor sound after it (original #980).

menuNextH/menuPrevH take menuSemaId, the lock the async config worker snapshots and publishes under,
so a tab move and a config publish cannot interleave. The cursor sound is an audsrv RPC; playing it
while holding that lock made every publish wait on audio. A NULL selection must not be dereferenced.
"""
from pathlib import Path
import re
import sys

source = (Path(__file__).resolve().parents[2] / 'src/ui/menusys.cpp').read_text(encoding='utf-8')
failures = []
for name, link in (('menuNextH', 'next'), ('menuPrevH', 'prev')):
    start = source.index('static void %s()' % name)
    body = source[start:source.index('\n}\n', start)]
    scope = re.search(r'\n    \{\n(.*?)\n    \}\n', body, re.S)
    if scope is None or 'raii::SemaLock lock(menuSemaId);' not in scope.group(1):
        failures.append('%s: the move must happen inside a menuSemaId scope' % name)
        continue
    if 'sfxPlay' in scope.group(1) or not re.search(r'\n    if \(moved\)\n        sfxPlay\(SFX_CURSOR\);', body):
        failures.append('%s: the cursor sound must play after the lock is released' % name)
    if 'selected_item != NULL ? selected_item->%s : NULL' % link not in scope.group(1):
        failures.append('%s: a NULL selection must not be dereferenced' % name)
    if 'itemConfigGeneration++' not in scope.group(1):
        failures.append('%s: a move must invalidate the pending config snapshot' % name)
if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('menu tab moves: locked publish, unlocked cursor sound, NULL selection guarded')
