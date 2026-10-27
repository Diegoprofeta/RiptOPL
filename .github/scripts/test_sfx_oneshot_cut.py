"""UI one-shot sounds share one voice, so the newest press cuts the previous one (original #1012).

The ps2build audsrv-compat header documents that audsrv_ch_play_adpcm(ch, ...) on channel 0-23
replaces what is playing there. One shared voice therefore gives the cut that the original needed a
fifteen-voice mute/restore pool for under stock audsrv, which refuses a busy voice. This checks the
source routing only; whether the replacement is audible as a clean cut needs a console.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[2]
sfx = (root / 'src/core/sfx.cpp').read_text(encoding='utf-8')
play = sfx[sfx.index('void SoundEffects::play(int id)'):]
play = play[:play.index('\n}\n')]

branch = re.search(r'else if \(sfxIsUiOneShot\(id\)\) \{(.*?)\n        \} else \{', play, re.S)
failures = []
if branch is None:
    failures.append('play(): the one-shot branch is not a separate else-if')
else:
    calls = re.findall(r'audsrv_ch_play_adpcm\(([^,]+),', branch.group(1))
    if calls != ['SFX_CANCEL']:
        failures.append('play(): one-shots must replay on the single shared voice, got %r' % calls)
    if 'SFX_ONESHOT_COALESCE_MS' not in branch.group(1):
        failures.append('play(): the same-frame double raise (#575) is no longer coalesced')

if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('UI one-shots: one shared voice, same-frame double raise coalesced')
