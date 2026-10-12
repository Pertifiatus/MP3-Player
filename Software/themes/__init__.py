"""Front-display designs (Einstellungen → Anzeige → Design), one module each - see
docs/superpowers/specs/2026-10-12-design-themes-design.md. Every module draws
the views from ui_views with its own layout; ui_render picks the active one.

Adding a design: new module here + entry in THEMES + its choice in
ui_state.THEME_CHOICES (test_ui_render checks both lists match)."""
from themes import cybercore, glass, klassik, neumorph, y2k

THEMES = {
    "klassik": klassik,
    "cybercore": cybercore,
    "y2k": y2k,
    "glass": glass,
    "neumorph": neumorph,
}


def get(name):
    return THEMES.get(name, klassik)
