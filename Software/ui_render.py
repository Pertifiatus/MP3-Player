"""Front-display rendering: builds the current screen's view (ui_views) and lets
the active design (themes/, Einstellungen → Anzeige → Design) draw it, then adds
the status-ring and Quick-Connect overlays."""
import themes
import ui_views
from ui_common import W

# UI-Groesse setting (1-5 stepper) -> layout density multiplier. 3 = 100%, matches
# every pixel constant in the designs as tuned. Below 1.0 shrinks fonts/rows/
# margins so more list content fits on screen; above 1.0 grows them for
# readability at the cost of items visible at once.
UI_SCALE_STEPS = {1: 0.75, 2: 0.88, 3: 1.0, 4: 1.15, 5: 1.3}


def _theme(state):
    return themes.get(state.settings.get("display", "theme"))


def _ctx(state):
    return ui_views.RenderCtx(UI_SCALE_STEPS[state.settings.get("display", "ui_scale")], ui_views.status(state))


def render(state):
    theme, ctx = _theme(state), _ctx(state)
    view = ui_views.build(state)
    img = getattr(theme, "draw_" + view.KIND)(view, ctx)
    if state.status_ring_visible():
        theme.draw_status(img, ctx.status, ctx)
    if state.qc_active:
        qc = ui_views.quick_connect(state)
        if qc is not None:
            theme.draw_quick_connect(img, qc, ctx)
    return img


def animating(state):
    """True while the active design is mid-animation and wants frames even
    without input - the Pixelhaus camera flight (see main.py)."""
    return getattr(_theme(state), "animating", lambda: False)()


def render_shutdown(state=None):
    """Standalone message screen for the power-button long-press (power_button.py) -
    not part of the screen/state machine (nothing to navigate back from)."""
    if state is None:
        return themes.klassik.draw_shutdown(None)
    return _theme(state).draw_shutdown(_ctx(state))
