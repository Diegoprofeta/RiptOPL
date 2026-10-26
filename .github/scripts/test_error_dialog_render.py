"""A context-free error must not render the active library or queue its artwork (original #1034).

The disc picker's errors are shown while the HDD leg has pfs0: remounted on the game partition; drawing
the menu behind the box could queue cover IO against that mount. With a caller-supplied UI the box keeps
that context; without one it paints its own opaque background and never calls guiShow().
"""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'src/ui/guimodal.cpp').read_text(encoding='utf-8')
start = source.index('void MessageBoxScreen::draw()')
draw = source[start:source.index('\n}', start) + 2]
assert 'guiShow()' not in draw, 'a context-free message box must not render the active menu'
assert 'diaRenderUI(ui_,' in draw, 'a supplied UI stays visible behind the box'
assert 'ui_ ? gColDarker : gColBlack' in draw, 'context-free errors get an opaque background'
print('PASS: error dialogs avoid active-menu rendering; supplied UI context preserved')
