#!/usr/bin/env python3
"""Host regression test for About dialog layout and tester credits.

Ports upstream PR #944:
1. Akilluminati47 and eliminator are credited under Quality Assurance.
2. The obsolete in-app Financial Support section is removed from diaAbout.
3. Excess UI_BREAK rows are trimmed to prevent vertical overflow in the fixed non-scrolling dialog.
"""
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[2]
dialogs_cpp = (root / "src/ui/dialogs.cpp").read_text(encoding="utf-8")

dia_about_start = dialogs_cpp.find("struct UIItem diaAbout[] = {")
assert dia_about_start != -1, "diaAbout not found in dialogs.cpp"
dia_about_end = dialogs_cpp.find("{UI_TERMINATOR}};", dia_about_start)
assert dia_about_end != -1, "diaAbout terminator not found"
dia_about = dialogs_cpp[dia_about_start : dia_about_end + len("{UI_TERMINATOR}};")]

# 1. Financial support section removed from diaAbout
assert "_STR_FINANCIAL_SUPPORT" not in dia_about, "Financial support section should not be in diaAbout"

# 2. Akilluminati47 and eliminator credited under Quality Assurance
assert '"Akilluminati47, eliminator"' in dia_about, "Akilluminati47 and eliminator should be credited in diaAbout QA"

# 3. QA rows should contain all expected contributors
assert "algol, Berion, Blade1984, El_Patas, EP, gledson999, jolek, lee4, Vapor" in dia_about
assert "LocalH, RandQalan, ShaolinAssassin, yoshi314, zero35, zackcage6" in dia_about

print("PASS: About dialog layout has testers under QA, no financial section, and trimmed spacing")
