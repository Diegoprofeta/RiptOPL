"""Right-to-left and CJK text ported from RIPPS2 (akilluminati47/RIPPS2, build 104).

1. txtShape joins Arabic and Persian letters (presentation forms, lam-alef as one) and lays each line out right to
   left; Latin words and numbers keep their order, brackets turn round, text without right-to-left letters is left
   alone. txtBreakAt allows a line break only between CJK, Thai or Lao letters, never before closing punctuation or a
   vowel that belongs to the letter before.
2. fntWrapText (the hint box and the message box) breaks CJK text between letters and an over-wide word anywhere,
   and never cuts a character when the buffer fills.
3. The font system draws and measures the shaped text, and skips zero-width marks.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
scripts = Path(__file__).resolve().parent
fnt = (root / 'src/gfx/fntsys.cpp').read_text()


def function(source, signature):
    pos = source.index(signature)
    start = source.index('{', pos)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[pos:i + 1]
    raise AssertionError('unterminated ' + signature)


def run(name, code):
    with tempfile.TemporaryDirectory(prefix='ripps2-text-') as temp:
        src = Path(temp) / (name + '.cpp')
        exe = Path(temp) / (name + '.exe')
        src.write_text(code)
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(root), str(src), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


shape_main = (scripts / 'ripps2_text_cases.inc').read_text()
run('shape', '#include "src/gfx/textshape.cpp"\n' + shape_main.split('/* ---- wrap ---- */')[0])
print('ok   Arabic and Persian joined and laid out right to left; CJK, Thai and Lao line breaks')

wrap = function(fnt, 'static int fntWrapPut(') + '\n\n' + function(fnt, 'int fntWrapText(')
mocks = '''#include <string.h>
#include "src/gfx/textshape.cpp"
static int rmUnScaleX(int x) { return x; }
static int fntCalcDimensions(int id, const char *s) /* 10 a Latin character, 20 any other */
{
    int w = 0;
    (void)id;
    while (*s) {
        uint32_t c;
        int n = txtNext(s, &c);
        w += c < 0x80 ? 10 : 20;
        s += n;
    }
    return w;
}
'''
run('wrap', mocks + wrap + '\n' + shape_main.split('/* ---- wrap ---- */')[1])
print('ok   fntWrapText: words, hard breaks, over-wide words, CJK breaks, full buffer')

render = function(fnt, 'int FontSystem::renderString(int id, int x, int y, short aligned, size_t width, size_t height, const char *string, u64 colour)')
assert render.index('calcDimensionsLocked(font, string)') < render.index('txtShape(string, shaped, sizeof(shaped), 1)'), 'measure, then shape for drawing'
assert 'txtZeroWidth(run.codepoint)' in render
calc = function(fnt, 'int FontSystem::calcDimensionsLocked(')
assert 'txtShape(str, joined, sizeof(joined), 0)' in calc and 'txtZeroWidth(codepoint)' in calc, 'measure the joined letters, skip zero-width marks'
assert '#ifndef __RTL' in calc, 'the old __RTL build keeps its own drawing'
dia = (root / 'src/ui/dia.cpp').read_text()
assert 'fntWrapText(gTheme->fonts[0], text, innerW, wrapped, sizeof(wrapped))' in function(dia, 'static void diaDrawHint(')
modal = (root / 'src/ui/guimodal.cpp').read_text()
assert 'return fntWrapText(gTheme->fonts[0], text, innerW, out, outSize);' in function(modal, 'int MessageBoxScreen::wrapText(')
assert 'src/gfx/textshape.cpp' in (root / 'ps2.yaml').read_text()
print('ok   the font system shapes and measures right-to-left text; hint and message boxes use fntWrapText')
