#!/usr/bin/env python3
"""Source-wiring regression checks for the per-game _LGO artwork toggle."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


class LogoArtToggle(unittest.TestCase):
    def test_default_enabled_and_persistence(self):
        opl = source("src/app/opl.cpp")
        config = source("include/config.h")
        settings = source("src/core/settings.cpp")
        self.assertIn('CONFIG_OPL_ENABLE_LOGOART             "enable_logoart"', config)
        self.assertIn("int gEnableLogoArt;", opl)
        self.assertIn("intSetting(CONFIG_OPL_ENABLE_LOGOART, &gEnableLogoArt, 1),", settings)

    def test_artwork_ui_reads_and_writes_toggle(self):
        dialogs = source("src/ui/dialogs.cpp")
        gui = source("src/ui/guisettings.cpp")
        self.assertIn("UICFG_ENABLE_LOGOART, 1, 1, _STR_HINT_LOGOART", dialogs)
        self.assertIn("_STR_LOGOART", dialogs)
        self.assertIn("diaSetInt(diaArtworkConfig, UICFG_ENABLE_LOGOART, gEnableLogoArt)", gui)
        self.assertIn("diaGetInt(diaArtworkConfig, UICFG_ENABLE_LOGOART, &gEnableLogoArt)", gui)

    def test_logo_and_disc_art_guarded_at_cache_and_draw_sites(self):
        themeelems = source("src/gfx/themeelems.cpp")
        coverflow = source("src/gfx/coverflow.cpp")
        self.assertIn('!gEnableDiscArt && strcmp(cache->suffix(), "ICO") == 0', themeelems)
        self.assertIn('!gEnableLogoArt && strcmp(cache->suffix(), "LGO") == 0', themeelems)
        self.assertIn("if (isHiddenArtworkCache(cache))", themeelems)
        self.assertIn("if (isHiddenArtworkCache(gameImage->cache))", themeelems)
        self.assertIn("if (!cimg || isHiddenArtworkCache(cimg->cache))", coverflow)
        self.assertGreaterEqual(themeelems.count("!isHiddenArtworkCache(itemsList->decoratorImage->cache)"), 3)
        self.assertNotIn("isDiscArtCache(", themeelems)

    def test_language_ids_are_appended(self):
        labels = source("lng/tmpl/_base.yml")
        self.assertLess(labels.index("- label: AUTO_VMC_STILL_RUNNING"), labels.index("- label: LOGOART"))
        self.assertLess(labels.index("- label: LOGOART"), labels.index("- label: HINT_LOGOART"))


if __name__ == "__main__":
    unittest.main()
