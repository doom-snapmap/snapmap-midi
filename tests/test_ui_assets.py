"""What the window's Javascript assumes about Python, checked as text.

There is no browser engine in this suite and there is not going to be one. The
whole shape of this feature exists to avoid needing one: Python owns every
decision the window shows, including the ruler's geometry, so what is left
untestable is markup and nothing else.

That split leaves exactly one seam, and this file is the only thing standing on
it. `app.js` names Python methods and reads Python dictionary keys, and it names
them as strings. A string that stopped naming anything does not raise here, or
in `tests/test_ui_api.py`, or anywhere else in this suite -- it fails in a
window, at a click, in front of somebody who has no console to read it in. The
Open button simply stops working.

So this reads the three assets as text and asserts against them, the way
snapmap-plus checks its own webview (`tests/theme_contract_test.c`): source-text
assertions, no browser, no DOM. It is a crude instrument. It is also the only
one that can see this class of failure at all.
"""

from __future__ import annotations

import base64
import hashlib
import re
import tomllib
from pathlib import Path

from snapmap_midi import settings as settings_module
from snapmap_midi.ui.api import Bridge
from snapmap_midi.ui.app import web_root, web_url
from snapmap_midi.ui.session import Session

_ROOT = Path(__file__).resolve().parents[1]

# Through `web_root()` rather than by walking up from this file. That function is
# what the window itself calls to find the markup, so asking it is what makes a
# rename of the folder fail here rather than at the next attempt to open a
# window -- where it renders as a blank page, because a browser engine handed a
# missing file draws an empty one perfectly happily.
_WEB = web_root()
_JS = (_WEB / "app.js").read_text(encoding="utf-8")
_HTML = (_WEB / "index.html").read_text(encoding="utf-8")
_CSS = (_WEB / "styles.css").read_text(encoding="utf-8")

_TINY_MIDI = str(Path(__file__).resolve().parent / "fixtures" / "tiny.mid")


def _pyproject() -> dict:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_every_bridge_method_the_window_calls_exists_and_is_callable():
    """The one assertion here that nothing else in the suite can make.

    `tests/test_ui_api.py` proves every `Bridge` method answers rather than
    raises. Nothing proves the window calls the methods that exist. A renamed
    method leaves `window.pywebview.api.old_name` undefined, and calling
    undefined is a `TypeError` inside a browser engine with no console attached:
    the button goes dead, no toast appears, and the window looks like it ignored
    the click.

    `assert called` comes first and is not decoration. This assertion is a loop
    over whatever the pattern found, so a pattern that stopped matching -- a
    refactor that routed calls through a local `var bridge = api();` -- would
    leave an empty list and a test that passes by checking nothing.
    """
    called = sorted(set(re.findall(r"api\(\)\.([A-Za-z_][A-Za-z0-9_]*)\(", _JS)))
    assert called, "no `api().<method>(` calls found in app.js -- this test stopped looking"
    for name in called:
        assert not name.startswith("_"), (
            "app.js calls %r, which is private; the bridge's public surface is the contract "
            "and a leading underscore says this one is not part of it" % name
        )
        method = getattr(Bridge, name, None)
        assert callable(method), "app.js calls api().%s(), which Bridge does not have" % name


def test_the_window_hard_codes_no_family_name():
    """Families come from `catalog()`, which derives them from the palette.

    A literal here would be a second source of truth, and the one that cannot be
    wrong is the palette: it is parsed from the shipped sound list, so a family
    that stops existing stops being offered. A name spelled into the window
    survives its own removal and reaches `validate` as a refusal the user did
    not cause.

    Note what this asserts and what an earlier draft asserted. That one checked
    that every `ins_` literal it found was a pitched family -- which is a loop
    over the literals, and there are none, so it passed without executing its
    body and would have gone on passing if somebody had added `ins_string` in a
    place the pattern happened not to reach. "Every literal is fine" and "there
    are no literals" look like the same claim and only the second one is worth
    making, because only the second one fails when the property breaks.
    """
    hard_coded = re.findall(r"['\"]ins_[a-z_]+['\"]", _JS + _HTML)
    assert not hard_coded, (
        "the window names %s; families come from catalog() so the palette stays the only "
        "source of truth" % ", ".join(sorted(set(hard_coded)))
    )


def test_the_markup_links_the_style_and_the_behaviour_beside_it():
    """Relative paths, because the window is loaded from a local file URI.

    Nothing is served: `webview.create_window` is handed the `file:///` URI for
    `index.html` and the engine resolves the two links against it. A link that
    no longer matches the file beside it does not raise -- the page renders
    unstyled and inert, which reads as the window having failed to load its data
    rather than its assets.
    """
    assert 'href="styles.css"' in _HTML
    assert 'src="app.js"' in _HTML


def test_midi_import_has_a_visible_long_running_state():
    """A dense import must not leave the unchanged Open card looking frozen."""
    assert 'id="midiLoadingState"' in _HTML
    assert 'role="status"' in _HTML
    assert 'aria-live="polite"' in _HTML
    assert ".midi-loading-spinner" in _CSS
    assert "setMidiLoading(true, 'Opening MIDI...'" in _JS
    assert "setMidiLoading(false)" in _JS


def test_the_window_entrypoint_is_a_file_uri_and_not_a_loopback_server():
    assert web_url() == (_WEB / "index.html").as_uri()
    assert web_url().startswith("file:///")
    assert "127.0.0.1" not in web_url()


def test_the_window_waits_for_the_bridge_instead_of_assuming_it():
    """`pywebviewready` is the only signal that `window.pywebview.api` exists.

    It fires after the document is parsed, so a window that read the bridge at
    `DOMContentLoaded` would find nothing there and open on its empty state with
    a song already loaded behind it.

    It is also what lets `index.html` be double-clicked. Off pywebview the event
    never arrives, `api()` stays null, and the window sits on "Open a MIDI file
    to begin" rather than throwing -- which is how anybody iterating on the
    markup or the stylesheet will open this file, and a version that threw would
    make that impossible without a Windows machine and a game install.
    """
    assert re.search(r"addEventListener\(\s*'pywebviewready'", _JS), (
        "app.js does not listen for pywebviewready; the bridge is not attached when the "
        "document finishes parsing"
    )


def test_reduced_motion_disables_decorative_transitions():
    """The playhead still moves because it carries song position; the drawer
    and toast transitions are decoration and honour the system preference."""
    assert "prefers-reduced-motion" in _CSS


def test_both_themes_are_defined():
    """Light and dark, because the toggle can reach either and the window ships
    with whichever the system reports.

    Compared with the whitespace stripped: a rule set is `:root {` here and
    `:root{` after a formatter, and a test that broke on that would be a test
    about how the file was typed. Losing `:root.dark` does not fail loudly --
    every custom property falls back to the light block, so the dark theme
    renders as light text on light panels.
    """
    stripped = re.sub(r"\s+", "", _CSS)
    assert ":root{" in stripped
    assert ":root.dark{" in stripped


def test_the_shared_snapmap_plus_design_tokens_do_not_drift():
    """Both windows use the exact same canonical light and dark palettes."""
    compact = re.sub(r"\s+", "", _CSS)
    canonical = [
        """
        :root {
          --bg:#eef0f3; --chrome:#f7f8fa; --panel:#ffffff; --panel2:#fbfbfc;
          --border:#e4e6ea; --border2:#d3d6db; --text:#1b1d21; --muted:#6b7280;
          --accent:#2f7ad6; --accentText:#ffffff; --sel:#e7f0fb; --selText:#123a63;
          --link:#2a68b8; --field:#ffffff; --danger:#a3352f;
          --tkKey:#0550ae; --tkStr:#9a3b22; --tkNum:#116329; --tkBool:#8250df;
          --sqErr:#d1372c; --sqWarn:#b58a1f; color-scheme: light;
        }
        """,
        """
        :root.dark {
          --bg:#191a1d; --chrome:#232428; --panel:#26272b; --panel2:#2b2d31;
          --border:#33353b; --border2:#45474e; --text:#e7e8ea; --muted:#9aa0a8;
          --accent:#4a9eff; --accentText:#0c1116; --sel:#2d4257; --selText:#cfe4fb;
          --link:#6fb2ff; --field:#1f2024; --danger:#c9483d;
          --tkKey:#7cb5ff; --tkStr:#ce9178; --tkNum:#9fd394; --tkBool:#c39ce8;
          --sqErr:#f14c4c; --sqWarn:#d7a944; color-scheme: dark;
        }
        """,
    ]
    for rule in canonical:
        assert re.sub(r"\s+", "", rule) in compact


def test_the_shared_snapmap_plus_shell_primitives_do_not_drift():
    """MIDI-specific rows may differ; shared chrome and controls may not."""
    compact = re.sub(r"\s+", "", _CSS)
    canonical = [
        (
            ".app { display:flex; flex-direction:column; height:100vh; "
            "background:var(--bg); color:var(--text); user-select:none; "
            "-webkit-user-select:none; }"
        ),
        (
            ".menubar { display:flex; align-items:center; height:30px; "
            "background:var(--chrome); border-bottom:1px solid var(--border); "
            "padding:0 6px; gap:8px; flex-shrink:0; user-select:none; }"
        ),
        (
            ".win-controls { display:flex; align-items:stretch; align-self:stretch; gap:0; "
            "margin-left:8px; margin-right:-6px; padding:0; }"
        ),
        (
            ".win-btn { width:38px; height:30px; display:flex; align-items:center; "
            "justify-content:center; padding:0 12px; border-radius:0; "
            "color:var(--muted); font-size:12px; "
            "cursor:default; }"
        ),
        ".win-btn:hover { background:var(--panel2); color:var(--text); }",
        ".panel-body.pad { padding:10px; }",
        ".list-empty { padding:10px; color:var(--muted); font-style:italic; }",
        ".btn.icon { padding:3px 8px; font-size:12px; }",
        (
            ".toast { min-width:150px; max-width:320px; padding:8px 12px; "
            "background:#333; color:#fff; border-radius:6px; font-size:11px;"
        ),
    ]
    for rule in canonical:
        assert re.sub(r"\s+", "", rule) in compact, rule.split("{")[0].strip()


def test_the_brand_mark_is_the_exact_snapmap_plus_asset():
    prefix = "data:image/jpeg;base64,"
    assert prefix in _HTML
    encoded = _HTML.split(prefix, 1)[1].split(chr(34), 1)[0]
    digest = hashlib.sha256(base64.b64decode(encoded)).hexdigest()
    assert digest == "3209c9dbad0ff5a63858c4ebb97cb5d059463768b8993919d59abc7dec51215b"


def test_the_custom_frame_has_every_snapmap_plus_move_and_resize_surface():
    for edge in ("t", "b", "l", "r", "tl", "tr", "bl", "br"):
        assert 'class="rz rz-%s"' % edge in _HTML
    for button in ("winMin", "winMax", "winClose"):
        assert 'id="%s"' % button in _HTML
    for call in ("win_drag", "win_resize", "win_min", "win_max", "win_close"):
        assert "api().%s(" % call in _JS


def test_the_interface_ships_only_its_curated_lucide_icon_subset():
    symbols = set(re.findall(r'<symbol id="icon-([a-z0-9-]+)"', _HTML))
    assert symbols == {
        "chevron-down",
        "chevron-left",
        "chevron-right",
        "circle-alert",
        "copy",
        "folder",
        "folder-open",
        "headphones",
        "minus",
        "music-2",
        "pause",
        "play",
        "search",
        "settings",
        "square",
        "triangle-alert",
        "volume-2",
        "volume-x",
        "x",
    }
    assert "lucide.min.js" not in _HTML
    assert "unpkg.com" not in _HTML
    for control in ("winMin", "winMax", "winClose", "transportPlay"):
        assert re.search(r'id="%s"[^>]*>.*?class="ui-icon"' % control, _HTML)
    assert "setIcon(el('winMax'), maximized ? 'copy' : 'square')" in _JS
    assert "setIcon(el('playGlyph'), AUDIO.playing ? 'pause' : 'play')" in _JS
    assert re.search(
        r'id="conversionBtn"[^>]*aria-label="Conversion settings"[^>]*>'
        r'.*?<use href="#icon-settings"></use>',
        _HTML,
    )
    license_text = (_WEB / "LUCIDE_LICENSE.txt").read_text(encoding="utf-8")
    assert "ISC License" in license_text
    assert "Lucide Icons and Contributors" in license_text


def test_the_workstation_is_one_surface_with_one_global_transport():
    assert 'id="trackList"' in _HTML
    assert 'id="pianoRoll"' in _HTML
    assert 'id="transportPlay"' in _HTML
    assert 'id="scrubber"' in _HTML
    assert _HTML.count('class="transport-play"') == 1
    assert "tabstrip" not in _HTML
    assert 'role="tab"' not in _HTML
    assert "preview_note" not in _JS
    assert _JS.count("api().preview_sound(") == 1
    assert 'id="soundBrowserOverlay"' in _HTML


def test_the_channel_sound_browser_is_a_lazy_searchable_file_explorer():
    for control in (
        "soundBrowserOverlay",
        "soundBrowserSearch",
        "soundTree",
        "soundResultList",
        "soundPagePrevious",
        "soundPageNext",
        "soundBrowserUse",
    ):
        assert 'id="%s"' % control in _HTML
    assert "api().sound_catalog()" in _JS
    assert "pageSize: 160" in _JS
    assert "makeSoundTree" in _JS
    assert "Search all DOOM soundbanks" in _JS
    assert "track-sound-picker" in _JS
    assert "event.previewable = event.previewable !== false" in _JS
    assert "audition.disabled = !previewable" in _JS
    assert "In-game only; local preview unavailable" in _JS
    assert "fillSoundPicker" not in _JS
    assert 'class="track-sound"' not in _HTML


def test_the_sound_browser_uses_the_snapmap_plus_modal_contract():
    assert ".modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45);" in _CSS
    assert (
        ".modal { background: var(--panel); border: 1px solid var(--border2); "
        "border-radius: 10px; padding: 16px 18px; "
        "box-shadow: 0 12px 34px rgba(0,0,0,0.42);"
    ) in _CSS
    assert 'class="modal sound-browser-modal"' in _HTML
    assert 'aria-modal="true"' in _HTML


def test_the_playhead_and_scrubber_both_seek_the_whole_song():
    for event in ("pointerdown", "pointermove", "pointerup", "pointercancel"):
        assert "canvas.addEventListener('%s'" % event in _JS
    assert "setPointerCapture" in _JS
    assert "context.lineTo(playheadX, height)" in _JS
    assert "requestAnimationFrame(animationTick)" in _JS
    assert "scrubber.addEventListener('input'" in _JS


def test_the_piano_roll_is_a_full_range_synchronized_scrollable_surface():
    for control in (
        "pianoRollViewport",
        "pianoRollExtent",
        "pianoRoll",
        "pitchRuler",
        "timeRuler",
    ):
        assert 'id="%s"' % control in _HTML
    assert "for (var pitch = 0; pitch <= 127; pitch += 1)" in _JS
    assert "context.fillText(noteName(pitch)" in _JS
    assert "128 * ROLL.rowHeight" in _JS
    assert "viewport.scrollTop" in _JS
    assert "viewport.scrollLeft" in _JS
    assert "el('pianoRollViewport').addEventListener('scroll', handleRollScroll)" in _JS
    assert re.search(r"\.roll-viewport\s*\{[^}]*overflow:\s*auto", _CSS)
    assert re.search(r"#pianoRoll\s*\{[^}]*position:\s*sticky", _CSS)


def test_the_workspace_and_notes_use_snapmap_plus_rounding_and_crisp_text():
    assert re.search(r"\.workspace\s*\{[^}]*border-radius:\s*8px", _CSS)
    assert "function roundedRectPath(context, x, y, width, height, radius)" in _JS
    assert "typeof context.roundRect === 'function'" in _JS
    assert "Math.min(4, eventWidth / 2, eventHeight / 2)" in _JS
    assert (
        "function fillNoteBlock(context, x, y, width, height, radius, color, alpha, glowing)" in _JS
    )
    assert re.search(
        r"fillNoteBlock\(\s*context,\s*geometry\.x,\s*geometry\.y,\s*geometry\.width,",
        _JS,
    )
    assert "context.fillRect(startX, eventY" not in _JS
    assert "context.imageSmoothingQuality = 'high'" in _JS
    assert "context.fontKerning = 'normal'" in _JS
    assert "context.textRendering = 'geometricPrecision'" in _JS
    assert "context.font = '600 ' + labelSize + 'px \"Segoe UI\"" in _JS
    assert "context.measureText(record.label).width <= geometry.width - 8" in _JS


def test_the_channel_roll_divider_resizes_both_panes_accessibly():
    assert 'id="tracksPane"' in _HTML
    assert 'id="paneSplitter" role="separator" tabindex="0"' in _HTML
    assert 'aria-orientation="vertical"' in _HTML
    assert re.search(
        r"\.pane-splitter\s*\{[^}]*flex:\s*0 0 9px;[^}]*cursor:\s*col-resize;"
        r"[^}]*touch-action:\s*none",
        _CSS,
    )
    assert "var TRACKS_MIN_WIDTH = 220" in _JS
    assert "var ROLL_MIN_WIDTH = 420" in _JS
    assert "available - ROLL_MIN_WIDTH" in _JS
    assert "workspace.style.setProperty('--tracks-width', width + 'px')" in _JS
    assert "localStorage.setItem(TRACKS_WIDTH_KEY" in _JS
    assert "splitter.setPointerCapture(event.pointerId)" in _JS
    for event in ("pointerdown", "pointermove", "pointerup", "pointercancel", "dblclick"):
        assert "splitter.addEventListener('%s'" % event in _JS
    for key in ("ArrowLeft", "ArrowRight", "Home", "End"):
        assert "event.key === '%s'" % key in _JS
    assert "constrainPaneSplit();\n      resizeCanvas();" in _JS


def test_piano_black_keys_and_the_scrollbar_corner_finish_the_rulers():
    assert "context.fillRect(isBlack ? 16" not in _JS
    assert "context.moveTo(isBlack ? 16" not in _JS
    assert "context.fillRect(0, y, width, ROLL.rowHeight)" in _JS
    # The 72px pitch-ruler gutter is open-mode only -- see .roll-pane--open --
    # so the base rule starts flush at 0 and only the open modifier pushes it
    # over, or lanes mode would leave that gutter's width sitting empty.
    assert re.search(
        r"\.roll-pane::after\s*\{[^}]*top:\s*0;[^}]*left:\s*0;[^}]*right:\s*0;"
        r"[^}]*height:\s*31px;[^}]*border-bottom:\s*1px solid var\(--border2\)",
        _CSS,
    )
    assert re.search(
        r"\.roll-pane\.roll-pane--open::after\s*\{[^}]*left:\s*72px",
        _CSS,
    )
    assert "context.moveTo(0, height - 0.5)" not in _JS


def test_playhead_dragging_pans_and_playback_locks_only_the_horizontal_scrollbar():
    assert 'id="horizontalScrollLock"' in _HTML
    assert "function canvasSeekScrollSpeed(clientX)" in _JS
    assert "requestAnimationFrame(continueCanvasSeekScroll)" in _JS
    assert "viewport.scrollLeft = clamp(before + speed" in _JS
    assert "setPosition(positionFromClientX(SEEK_DRAG.clientX), false)" in _JS
    assert "function renderHorizontalScrollLock()" in _JS
    assert "var height = Math.max(0, viewport.offsetHeight - viewport.clientHeight)" in _JS
    assert "var width = Math.max(0, viewport.offsetWidth - viewport.clientWidth)" in _JS
    assert "var locked = (ROLL_PART || ROLL_GLOBAL) && AUDIO.playing && height > 0" in _JS
    assert "lock.style.right = width + 'px'" in _JS
    # left:0 by default, same reasoning as .roll-pane::after: the 72px
    # pitch-ruler gutter is open-mode only, so this only gets pushed over
    # when .roll-pane--open is present.
    assert re.search(
        r"\.horizontal-scroll-lock\s*\{[^}]*position:\s*absolute;[^}]*z-index:\s*6;"
        r"[^}]*left:\s*0;[^}]*bottom:\s*0;[^}]*background:\s*var\(--scrollDisabled\);"
        r"[^}]*cursor:\s*default;[^}]*pointer-events:\s*auto",
        _CSS,
    )
    assert re.search(
        r"\.roll-pane\.roll-pane--open \.horizontal-scroll-lock\s*\{[^}]*left:\s*72px",
        _CSS,
    )


def test_scroll_redraws_are_coalesced_and_preserve_vertical_wheel_input():
    assert "var DRAW_FRAME = null" in _JS
    assert "cancelAnimationFrame(DRAW_FRAME)" in _JS
    assert "DRAW_FRAME = requestAnimationFrame(function ()" in _JS
    assert "function handleRollScroll()" in _JS
    assert re.search(r"function handleRollScroll\(\)\s*\{\s*queueDraw\(\);\s*\}", _JS)
    assert "addEventListener('scroll', handleRollScroll)" in _JS
    assert "function lockedWheelPixels(event, viewport)" in _JS
    assert "event.deltaMode === 1" in _JS
    assert "event.deltaMode === 2" in _JS
    assert "function forwardLockedScrollWheel(event)" in _JS
    assert "viewport.scrollTop += lockedWheelPixels(event, viewport)" in _JS
    assert "event.preventDefault()" in _JS
    assert re.search(
        r"horizontalScrollLock'\)\.addEventListener\('wheel', "
        r"forwardLockedScrollWheel, \{\s*passive: false",
        _JS,
    )


def test_roll_grid_meter_and_zoom_are_view_controls_in_the_control_plane():
    for control in (
        "globalRollToggle",
        "gridResolution",
        "timeSignature",
        "rollZoom",
        "rollZoomValue",
    ):
        assert 'id="%s"' % control in _HTML
    for resolution in ("1", "2", "4", "8", "16", "32"):
        assert 'option value="%s"' % resolution in _HTML
    for meter in ("2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "9/8", "12/8"):
        assert 'option value="%s"' % meter in _HTML
    # Above ~4,222% a browser canvas reaches a dimension it cannot render on
    # some GPUs. Keep the control just under that point instead of accepting a
    # zoom level that turns the lane clips white.
    assert 'id="rollZoom" min="0" max="53"' in _HTML
    assert "function toggleGlobalRoll()" in _JS
    assert "ROLL_GLOBAL = !ROLL_GLOBAL" in _JS
    assert "ROLL_GLOBAL ? source" in _JS
    assert "globalRollToggle').addEventListener('click', toggleGlobalRoll)" in _JS
    assert "ROLL_PART || ROLL_GLOBAL" in _JS
    assert "gridDenominator = Math.max(1, Number(gridDenominator) || ROLL.gridDenominator);" in _JS
    assert "ticksPerBeat * 4 / gridDenominator" in _JS
    assert "laneGridDenominator: 1" in _JS
    assert "var laneLines = timingLinesAt(scrollLeft, visibleWidth, ROLL.laneGridDenominator);" in _JS
    assert "function activeGridDenominator()" in _JS
    assert "return ROLL_PART || ROLL_GLOBAL ? ROLL.gridDenominator : ROLL.laneGridDenominator;" in _JS
    assert "ticksPerBeat * 4 / ROLL.meterDenominator * ROLL.meterNumerator" in _JS
    assert "timeAtTick(tick)" in _JS
    assert "Math.pow(2, stops / 10) * 100" in _JS
    assert "Math.min(3, 1 + Math.log(timeScale) / Math.LN2 * 0.4)" in _JS
    assert "ROLL.rowHeight = baseRowHeight * pitchScale" in _JS
    assert "ROLL.contentWidth = Math.max(width, width * timeScale)" in _JS
    assert "ROLL.contentHeight = Math.max(height, 128 * ROLL.rowHeight)" in _JS


def test_zoomed_playback_follows_the_sweeping_playhead():
    assert "function playheadZoomAnchor()" in _JS
    assert "var viewportX = contentXAtTime(position) - viewport.scrollLeft" in _JS
    assert "viewportX = viewport.clientWidth / 2" in _JS
    assert "contentXAtTime(zoomAnchor.position) - zoomAnchor.viewportX" in _JS
    assert "var zoomAnchor = playheadZoomAnchor()" in _JS
    assert "resizeCanvas(zoomAnchor)" in _JS
    assert "function revealPlayhead(position, following)" in _JS
    assert "if (AUDIO.playing) { revealPlayhead(position, true); }" in _JS
    # Following holds its screen position at the edge where it crossed; it
    # must not snap the playhead back from 78% to a separate 32% anchor.
    assert "var leadingAnchor = ROLL.viewportWidth * 0.78" in _JS
    assert "var trailingAnchor = ROLL.viewportWidth * 0.18" in _JS
    assert "x - (x > leadingEdge ? leadingAnchor : trailingAnchor)" in _JS
    assert "ROLL.contentWidth - ROLL.viewportWidth" in _JS
    assert "function contentXAtTime(timeMs)" in _JS
    assert "var startX = contentXAtTime(record.start)" in _JS
    assert "var playheadX = contentXAtTime(position)" in _JS
    assert "function audibleContextTime()" in _JS
    assert "AUDIO.context.getOutputTimestamp()" in _JS
    assert "audibleContextTime() - AUDIO.anchorTime" in _JS


def test_note_glow_is_hover_only_and_the_playhead_stays_independent():
    position = (
        "var position = positionOverride === undefined ? currentPosition() : positionOverride"
    )
    hovered = "var hovered = hoveredRenderEvent(el('pianoRoll'))"
    playhead = "var playheadX = contentXAtTime(position)"
    assert position in _JS
    assert hovered in _JS
    assert playhead in _JS
    assert _JS.index(hovered) < _JS.index(playhead) < _JS.index(position)
    assert "var active = AUDIO.playing" not in _JS
    assert "var glowing = active || hovered" not in _JS
    assert "context.shadowColor = color" in _JS
    assert "context.shadowBlur = 7" in _JS
    assert "context.globalAlpha = 0.16" in _JS
    assert "var point = pianoRollPointer(canvas)" in _JS
    assert "point.x >= geometry.x && point.x <= geometry.x + geometry.width" in _JS
    assert "point.y >= geometry.y && point.y <= geometry.y + geometry.height" in _JS
    assert re.search(
        r"function updateNotePointer\(event\).*?NOTE_POINTER = .*?;\s*queueDraw\(\);",
        _JS,
        re.DOTALL,
    )
    assert "canvas.addEventListener('pointermove', updateNotePointer)" in _JS
    assert "canvas.addEventListener('pointerleave', clearNotePointer)" in _JS


def test_clicking_a_note_opens_the_expression_inspector_and_empty_space_still_seeks():
    assert 'class="roll-help"' not in _HTML
    assert ".roll-help" not in _CSS
    for control in (
        "noteInspector",
        "closeNoteInspector",
        "noteSourcePitch",
        "noteSound",
        "notePitchRange",
        "notePitchMode",
        "notePitchNumber",
        "noteVolumeRange",
        "noteVolumeNumber",
        "noteClampNotice",
        "resetNoteExpression",
    ):
        assert 'id="%s"' % control in _HTML

    assert 'class="inspector note-inspector"' in _HTML
    assert ".channel-inspector, .note-inspector { width: 390px; }" in _CSS
    assert 'id: String(event.id || "")' in _JS
    assert "openNoteInspector(hit.record.id)" in _JS
    assert "pausePlayback();\n      openNoteInspector(hit.record.id)" in _JS
    assert "SEEK_DRAG = {" in _JS
    # Shared by the roll canvas, the ruler, and the lanes -- see
    # beginTimelineSeek/moveCanvasSeek -- so a click on any of the three
    # seeks the same way.
    assert "setPosition(positionFromClientX(event.clientX), false)" in _JS
    assert "function beginTimelineSeek(event, suppressMouse, captureTarget)" in _JS
    assert "function beginLaneTimelineSeek(event)" in _JS
    assert 'var lane = event.target.closest(".lane-row");' in _JS
    assert "beginTimelineSeek(event, false, lane);" in _JS
    assert "applyPatch({ notes: notePatch }, true)" in _JS
    assert "notePatch[SELECTED_NOTE_ID] = null" in _JS
    assert ">Pitch</label>" in _HTML
    assert 'id="notePitchReadout"' not in _HTML
    assert 'MIDI " + noteName(note.source_pitch) + " - "' not in _JS
    assert ">Note volume</label>" in _HTML
    assert "Number(note.note_volume_db || 0)" in _JS
    assert "entry[key] = value;" in _JS
    assert "entry.volume_trim_db = null;" in _JS
    assert "noteVelocity" not in _HTML
    assert "Velocity " not in _JS
    assert "context.strokeStyle = palette.accent" in _JS


def test_channel_strip_separates_focus_from_multi_solo_and_mute():
    assert 'actions.appendChild(mixerButton("mute", "muted"))' in _JS
    assert 'actions.appendChild(mixerButton("solo", "soloed"))' in _JS
    assert 'setIcon(mute, entry.muted ? "volume-x" : "volume-2")' in _JS
    assert 'iconElement(kind === "mute" ? "volume-2" : "headphones")' in _JS
    assert 'id="icon-volume-x"' in _HTML
    assert 'id="icon-headphones"' in _HTML
    # Focus is a PART, not a channel: two tracks can share channel 0, and
    # comparing channel numbers would select and dim both of them together.
    assert "openChannelInspector(channel.key)" in _JS
    assert re.search(r"SELECTED_PART = null;\s+closeChannelInspector\(\);", _JS)
    # A detailed track roll filters structurally, while the global roll uses
    # the exact same renderer with the complete event set.
    assert "var source = rollDisplayEvents();" in _JS
    assert "return String(event.part || (Number(event.channel) || 0)) === ROLL_PART;" in _JS
    assert "var filtered = ROLL_GLOBAL ? source : ROLL_PART" in _JS
    assert "STATE.preview.display_events" in _JS
    assert "record.muted || record.soloExcluded || !record.audible || !record.converted" in _JS
    assert ".track-row.muted-track .track-channel" in _CSS


def test_track_rows_double_click_to_toggle_roll_and_switch_on_click_when_open():
    assert 'name.addEventListener("dblclick"' in _JS
    assert 'row.addEventListener("dblclick"' in _JS
    assert "toggleTrackRoll(channel.key);" in _JS
    assert "if (ROLL_PART && !ROLL_GLOBAL)" in _JS
    assert "function openTrackRoll(partKey)" in _JS
    assert "use the gear for track settings" in _JS
    assert "function focusTrackRoll(channel)" in _JS
    assert "focusTrackRoll(channel);" in _JS
    assert "setRollZoomPercent(100 * clamp(duration / span * 0.84, 1, 8));" in _JS


def test_every_track_has_an_explicit_settings_action_in_both_roll_modes():
    assert 'track-settings-button' in _JS
    assert 'settingsButton.title = "Track settings"' in _JS
    assert 'settingsButton.appendChild(iconElement("settings"))' in _JS
    assert 'openChannelInspector(channel.key);' in _JS
    assert 'closeChannelInspectorAndClearSelection();' in _JS
    assert (
        'trackSettingsButton.setAttribute("aria-pressed", settingsOpen ? "true" : "false")'
        in _JS
    )
    assert (
        'trackSettingsButton.title = settingsOpen ? "Close track settings" : "Track settings"'
        in _JS
    )
    assert '.track-settings-button { opacity: .62; }' in _CSS
    assert ".track-mute-toggle.active" in _CSS
    assert re.search(r"\.track-row\s*\{[^}]*cursor:\s*pointer", _CSS)


def test_the_script_never_reads_a_name_it_does_not_declare():
    """Every other assertion here checks that `app.js` CONTAINS some text, and
    none of them can see a rename that missed one use. The file still parses,
    still holds every pinned string, and throws `ReferenceError` the first time
    the missed line runs. `patchTracks` kept one `channelNumber` after the rest
    of it moved to part keys; it sits in the render path, so every control in
    the window went dead while this suite stayed green.
    """
    from tests.js_scope import undeclared

    assert undeclared(_JS) == set()


def test_channel_settings_exposes_analysis_calibration_and_track_pitch():
    for control in (
        "channelInspector",
        "closeChannelInspector",
        "channelInspectorSubtitle",
        "channelPitchFollow",
        "channelPitchModeHelp",
        "channelPitchRegular",
        "channelAnalyzePitch",
        "channelClearPitch",
        "channelPitchAnalysis",
        "channelCalibrationRange",
        "channelCalibrationNumber",
        "channelCalibrationCentsRange",
        "channelCalibrationCentsNumber",
        "channelCalibrationHelp",
        "channelRootLabel",
        "channelRootValue",
        "channelRootDescription",
        "channelTransposeRange",
        "channelTransposeNumber",
        "channelGlideRange",
        "channelGlideNumber",
        "channelEffectivePitch",
        "channelAdvancedSettings",
        "channelSound",
        "channelMidiRange",
        "channelNoteCount",
    ):
        assert 'id="%s"' % control in _HTML

    assert 'aria-label="Track settings"' in _HTML
    assert "function syncChannelInspector()" in _JS
    assert "function openChannelInspector(partKey)" in _JS
    assert "function updateSelectedChannelPitchFollow(enabled)" in _JS
    assert "updateSelectedChannelPitchFollow(this.checked)" in _JS
    # Available for every exact sound, including one nothing could measure a
    # musical root for. Pitching an unmusical effect across the keyboard is
    # the point of the switch, and gating it on a detected root removed it.
    assert "follow.disabled = !exact;" in _JS
    assert 'el("channelPitchRegular").hidden = !exact;' in _JS
    assert 'el("channelPitchAdvanced").hidden = !exact;' in _JS
    assert '<summary>Advanced track settings</summary>' in _HTML
    advanced = _HTML.index('id="channelAdvancedSettings"')
    for regular_control in (
        "channelPitchFollow",
        "channelAnalyzePitch",
        "channelTransposeRange",
        "channelVolumeRange",
    ):
        assert _HTML.index('id="%s"' % regular_control) < advanced
    for advanced_control in (
        "channelCalibrationRange",
        "channelGlideRange",
        "channelAttackRange",
        "channelVoicesRange",
        "channelPolyRange",
        "channelSustainRange",
        "channelReleaseRange",
    ):
        assert _HTML.index('id="%s"' % advanced_control) > advanced
    assert ".channel-advanced-settings[open] > summary::after" in _CSS
    assert "var NEUTRAL_ROOT_MIDI = 60;" in _JS
    assert "follow.checked = exact ? !!entry.pitch_follow : !channel.is_drums" in _JS
    # The rootless reference is written through the part key, not a bare channel
    # number -- two tracks can share a channel, so the number is not an address.
    assert "body.root_midi = NEUTRAL_ROOT_MIDI;" in _JS
    assert "body.root_confidence = 0;" in _JS
    assert 'body.root_source = "neutral";' in _JS
    # Follow MIDI remains an explicit setting after selection; choosing a new
    # exact sound resets it instead of analyzing/tuning behind the user's back.
    assert "pitch_follow_preference: !!enabled" in _JS
    assert "savedPart.pitch_follow_preference" not in _JS
    assert "Automatic percussion selects a dedicated sound for each MIDI key" in _JS
    assert "Follow MIDI note uses an assumed " in _JS
    assert "neutral C4 reference" not in _JS
    assert 'id="notePitchFollow"' not in _HTML
    assert 'id="noteRootNumber"' not in _HTML
    assert "function analyzeSelectedChannelPitch()" in _JS
    assert "function clearSelectedChannelPitch()" in _JS
    assert 'el("channelClearPitch").addEventListener("click", clearSelectedChannelPitch)' in _JS
    assert "Clear pitch setup removes analysis and manual calibration" in _HTML
    assert "Pitch analysis and calibration cleared. The sound now plays unchanged." in _JS
    assert "pitch_follow: false," in _JS
    assert "root_midi: null," in _JS
    assert "function parsePitchReference(raw)" in _JS
    assert 'api().sound_profile(saved.sound, channel.key, true)' in _JS
    assert 'root_source: "manual"' in _JS
    assert 'id="notePitchRange" min="-24" max="24" step="1"' in _HTML
    assert 'id="notePitchNumber" min="-24" max="24" step="1"' in _HTML
    assert (
        "Adjusts this note in whole semitones. Use Sample tuning fine adjustment "
        "for cents across the track." in _HTML
    )
    assert 'return pitchName(value) + " (MIDI " + Math.round(Number(value)) + ")";' in _JS
    assert "function pitchAdjustment(value)" in _JS
    assert "? clamp(Math.round(numeric), limits[0], limits[1])" in _JS
    assert "Finds the sound's natural note and cents offset." in _HTML
    assert "Confidence shows how reliable the detection is." in _HTML
    assert 'id="channelPlayReference">Play C4 reference</button>' in _HTML
    assert "MIDI 60 \u00b7 261.63 Hz" in _HTML
    assert "Loops a built-in pure tone until you press Stop." in _HTML
    assert "function playPitchReferenceTone()" in _JS
    assert 'oscillator.type = "sine"' in _JS
    assert "440 * Math.pow(2, (60 - 69) / 12)" in _JS
    assert "oscillator.stop(now + 1.52)" not in _JS
    assert 'el("channelPlayReference").addEventListener("click", togglePitchReferenceTone)' in _JS
    assert "stopPitchReferenceTone();\n    CHANNEL_INSPECTOR_OPEN = false;" in _JS
    assert "Coarse sample tuning" in _HTML
    assert "Positive pitches the sample higher; negative pitches it lower." in _HTML
    assert "Sample tuning fine adjustment" in _HTML
    assert 'id="channelCalibrationRange" min="-24" max="24" step="1"' in _HTML
    assert 'id="channelCalibrationCentsRange" min="-100" max="100" step="1"' in _HTML
    assert "function updateManualSampleCalibration()" in _JS
    assert "var root = Math.round((NEUTRAL_ROOT_MIDI - correction) * 10000) / 10000" in _JS
    assert "pitch_follow_preference: true" in _JS
    assert 'root_source: "manual"' in _JS
    assert "var sendCalibration = debounce(updateManualSampleCalibration, 180)" in _JS
    assert 'placeholder="60 or C4 (optional)"' in _HTML
    assert "Shows the analyzer result or the note inferred from manual sample tuning." in _HTML
    assert "Edit it only when you already know the sound's natural note." in _HTML
    assert "Correction equals the imported MIDI note minus this value." in _HTML
    assert 'el("channelRootLabel").textContent = neutralReference' in _JS
    assert "Sample root (optional)" in _JS
    assert "No sample root has been set." in _JS
    assert "root === null || !isFinite(root) || neutralReference" in _JS
    assert 'noteName(NEUTRAL_ROOT_MIDI) + " reference; the raw sound plays unchanged there."' in _JS
    assert "Not analyzed. Follow MIDI note uses an assumed" in _JS
    assert 'noteName(60) + " automatic correction: "' in _JS
    assert "pitchAdjustment(referenceCorrection)" in _JS
    assert '"Pitch formula: imported MIDI note − " + pitchName(root)' in _JS
    assert "pitchAdjustment(referenceCorrection + adjustment)" in _JS
    assert "Moves every note on this track up or down in whole semitones." in _HTML
    assert "channelFineTuneRange" not in _HTML
    assert "channelFineTuneNumber" not in _HTML
    assert 'partPatch(channel, { fine_tune_cents: value })' not in _JS
    assert "Saved legacy track detune:" in _JS
    assert "A saved legacy detune adds" in _JS
    assert 'root_source: "manual",\n      fine_tune_cents: 0' in _JS
    assert "Pitches the sound to match each imported MIDI note." in _JS
    assert "Sound selected unchanged." in _JS
    assert "relative_anchor" not in _JS
    assert "Stable pitch detected for natural playback" not in _JS
    assert "function closeChannelInspectorAndClearSelection()" in _JS
    assert re.search(
        r"function closeChannelInspectorAndClearSelection\(\)\s*\{\s*"
        r"SELECTED_PART = null;\s*closeChannelInspector\(\);",
        _JS,
    )
    assert re.search(
        r'el\("closeChannelInspector"\)\.addEventListener\(\s*"click",\s*'
        r"closeChannelInspectorAndClearSelection\s*\)",
        _JS,
    )


def test_notes_advertise_clickability_only_when_pointer_hit_testing_finds_one():
    assert re.search(r"#pianoRoll\.note-hover\s*\{[^}]*cursor:\s*pointer", _CSS)
    assert '"note-hover",\n      !!hoveredRenderEvent(el("pianoRoll"))' in _JS
    assert 'el("pianoRoll").classList.remove("note-hover")' in _JS


def test_preview_uses_the_compiler_pitch_and_volume_values_without_rederiving_them():
    assert "source.playbackRate.value = playbackRate" in _JS
    assert "var playbackRate = Number(event.playback_rate || 1)" in _JS
    assert "offset = wallOffset * playbackRate" in _JS
    assert "source.playbackRate.linearRampToValueAtTime(" in _JS
    assert "var glideSeconds = Math.max(0, Number(event.glide_ms || 0) / 1000)" in _JS
    assert "var naturalDuration = buffer.duration / playbackRate" in _JS
    assert "if (wallOffset >= total) { return; }" in _JS
    assert "Math.pow(10, Number(event.volume_db || 0) / 20)" in _JS
    assert "api().sound_profile(candidate.value, partKey)" not in _JS
    assert "body.pitch_follow = false;" in _JS
    assert "body.pitch_follow_preference = false;" in _JS
    assert "body.root_midi = null;" in _JS
    assert "body.detected_root_midi = null;" in _JS
    assert "body.fine_tune_cents = 0;" in _JS
    assert (
        "Sound selected unchanged. Analyze or tune it only when you want pitch following."
        in _JS
    )
    assert "var activePitch = note.pitch_semitones;" in _JS
    assert 'Math.round(Number(activePitch) || 0)' in _JS
    assert "function notePitchOverrideKey(noteId)" in _JS
    assert 'return note.pitch_follow ? "follow_pitch_semitones" : "pitch_semitones"' in _JS
    assert 'key === "pitch_semitones" || key === "follow_pitch_semitones"' in _JS
    assert "entry[key] = value" in _JS
    assert "entry.pitch_offset = null" not in _JS
    assert '(note.pitch_follow ? "Follow MIDI" : "Manual") + " / semitones"' in _JS
    assert "notePitchOverrideKey(SELECTED_NOTE_ID)" in _JS


def test_settings_edits_coalesce_stale_slider_values_and_chrome_hover_states():
    assert "var PATCH_QUEUE = Promise.resolve();" in _JS
    assert "var PATCH_IN_FLIGHT = false;" in _JS
    assert "var PATCH_NEXT = null;" in _JS
    assert "PATCH_NEXT = mergePendingPatch(PATCH_NEXT, patch);" in _JS
    assert "function drainPatchQueue()" in _JS
    assert "key === 'drum_keys' || key === 'family_caps'" in _JS
    assert "pitch_follow_preference: !!enabled" in _JS
    assert ".menu-label { min-width: 36px; height: 24px;" in _CSS
    assert "border-radius: 5px; background: transparent" in _CSS
    assert ".close-button { width: 27px; height: 27px;" in _CSS
    assert "#winClose:hover { background:var(--danger); color:#fff; }" in _CSS
    assert ".tool-button.primary:hover:not(:disabled) { filter: brightness(1.16); }" in _CSS


def test_sound_browser_only_enables_use_for_a_new_selection():
    assert "function soundCandidateChanged()" in _JS
    assert 'el("soundBrowserUse").disabled = !soundCandidateChanged();' in _JS
    assert "if (!soundCandidateChanged()) { return; }" in _JS
    assert ".btn.primary:hover:not(:disabled) { filter: brightness(1.16); }" in _CSS


def test_window_controls_are_flush_square_and_optically_balanced():
    assert (
        ".win-controls { display:flex; align-items:stretch; align-self:stretch; "
        "gap:0; margin-left:8px; margin-right:-6px; padding:0; }"
    ) in _CSS
    assert (
        ".win-btn { width:38px; height:30px; display:flex; align-items:center; "
        "justify-content:center; padding:0 12px; border-radius:0;"
    ) in _CSS
    assert "#winClose .ui-icon { width: 18px; height: 18px; }" in _CSS


def test_natural_song_completion_does_not_hard_stop_finite_audio_tails():
    assert "function stopPlaybackClock()" in _JS
    assert re.search(
        r"function animationTick\(\).*?if \(position >= duration\) \{\s*"
        r"finishPlayback\(\);",
        _JS,
        re.DOTALL,
    )
    finish = re.search(
        r"function finishPlayback\(\) \{(?P<body>.*?)\n  \}",
        _JS,
        re.DOTALL,
    )
    assert finish
    assert "stopPlaybackClock();" in finish.group("body")
    assert "stopSources();" not in finish.group("body")
    assert re.search(
        r"stopSources\(\);\s*AUDIO\.performance = capturePlaybackPreview\(\);\s*"
        r"AUDIO\.playing = true;",
        _JS,
    )


def test_octave_labels_are_a_display_only_view_preference():
    assert 'id="menuMiddleC4" role="menuitemradio"' in _HTML
    assert 'id="menuMiddleC3" role="menuitemradio"' in _HTML
    assert "var OCTAVE_LABEL_KEY = 'snapmap_midi_middle_c_octave'" in _JS
    assert "var octave = Math.floor(note / 12) + MIDDLE_C_OCTAVE - 5" in _JS
    assert "setMiddleCOctave(4, true, true)" in _JS
    assert "setMiddleCOctave(3, true, true)" in _JS
    expression_source = (_ROOT / "src" / "snapmap_midi" / "music" / "expression.py").read_text(
        encoding="utf-8"
    )
    assert "MIDDLE_C_OCTAVE" not in expression_source


def test_bottom_control_plane_exposes_the_persisted_master_volume():
    assert 'id="masterVolume" min="-60" max="20"' in _HTML
    assert 'id="masterVolumeValue"' in _HTML
    assert 'class="range-control master-volume-control"' in _HTML
    assert 'class="range-control zoom-control"' in _HTML
    assert _HTML.index('id="rollZoom"') < _HTML.index('id="rollZoomValue"')
    assert ".range-control" in _CSS
    assert ".master-volume-control .ui-icon" not in _CSS
    assert "applyPatch({ tuning: { master_volume_db: value } }, true)" in _JS
    assert "paintMasterVolume(tuning().master_volume_db)" in _JS
    assert "el('masterVolume').disabled = !song" in _JS
    assert '"Track " + signed(note.track_volume_db)' in _JS
    assert 'signed(note.master_volume_db)' in _JS
    assert '" dB; output " + signed(note.volume_db)' in _JS


def test_the_playhead_and_hover_use_lightweight_overlay_canvases():
    for control in ("pianoRollOverlay", "timeRulerOverlay"):
        assert 'id="%s"' % control in _HTML
        assert "sizeCanvas(el('%s')" % control in _JS
    assert re.search(
        r"\.roll-overlay\s*\{[^}]*z-index:\s*4;[^}]*pointer-events:\s*none",
        _CSS,
    )
    assert "function drawRollOverlays(position, palette)" in _JS
    assert "if (RENDER.surfaceDirty) { drawStaticRoll(lines, palette); }" in _JS
    assert "drawRollOverlays(position, palette)" in _JS
    assert _JS.index("if (RENDER.surfaceDirty)") < _JS.rindex("drawRollOverlays(position, palette)")


def test_track_lanes_expose_a_synchronized_horizontal_scrollbar():
    assert re.search(r"\.lanes-view:not\(\[hidden\]\).*overflow:\s*auto", _CSS)
    assert _CSS.count("scrollbar-gutter: stable") >= 2
    assert "lanes.scrollLeft = viewport.scrollLeft" in _JS
    assert "viewport.scrollLeft = lanes.scrollLeft" in _JS
    assert "if (!el('lanesView').hidden) { patchLanesView(); }" in _JS
    assert "function laneDisplayEvents(partKey)" in _JS
    assert "var LANE_EVENTS_CACHE = { source: null, byPart: null };" in _JS
    assert "var events = laneDisplayEvents(channel.key);" in _JS
    assert "var laneLines = timingLinesAt(scrollLeft, visibleWidth, ROLL.laneGridDenominator);" in _JS
    assert "function timingLinesAt(scrollLeft, viewportWidth, gridDenominator)" in _JS
    assert "function drawLaneTimingGrid(context, lines, width, height, palette)" in _JS
    assert "drawLaneTimingGrid(context, lines, width, height, palette);" in _JS
    assert 'fill.className = "lane-grid-fill";' in _JS
    assert "function drawLaneGridFill(canvas, width, height, scrollLeft, lines, palette)" in _JS
    assert "var fillHeight = Math.max(0, container.clientHeight - usedHeight);" in _JS
    assert ".lane-grid-fill {" in _CSS
    assert "background: color-mix(in srgb, var(--track-color) 6%, var(--field));" in _CSS
    assert "border-left: 2px solid var(--track-color);" in _CSS
    assert "context.fillStyle = trackColor;" in _JS
    assert "context.strokeStyle = trackColor;" in _JS
    assert "var limited = [];" in _JS
    assert "limited.push({ x: x, y: y, width: w, height: rowHeight });" in _JS
    assert "context.setLineDash([3, 2]);" in _JS
    assert "queueLaneDraw();\n      queueDraw();" in _JS
    assert "var x = (start / duration) * contentWidth - scrollLeft" in _JS


def test_space_is_reserved_for_transport_outside_typing_fields():
    assert "input[type=\"text\"], input[type=\"search\"], textarea" in _JS
    assert "if (!typing && event.code === 'Space')" in _JS
    assert "Promise.resolve(context.resume())" in _JS
    assert "if (event.key === 'Enter') { event.preventDefault(); action(); }" in _JS
    chrome_keyboard = re.search(
        r"function keyboardClick\(node, action\) \{(?P<body>.*?)\n  \}",
        _JS,
        re.DOTALL,
    )
    assert chrome_keyboard
    assert "event.key === ' '" not in chrome_keyboard.group("body")


def test_track_settings_expose_a_persisted_track_volume_layer():
    assert 'id="channelVolumeRange" min="-60" max="20"' in _HTML
    assert 'id="channelVolumeNumber" min="-60" max="20"' in _HTML
    assert "applyPatch(partPatch(part, { volume_db: value }), true)" in _JS
    assert "syncChannelVolume(channel)" in _JS


def test_release_has_a_song_default_and_optional_track_override():
    assert '<label for="releaseRange">Default Track Release</label>' in _HTML
    assert "Fades sustained or looping notes after MIDI note-off" in _HTML
    assert 'id="channelReleaseEnabled"' in _HTML
    assert 'id="channelReleaseRange" min="0" max="2" step="0.01"' in _HTML
    assert 'id="channelReleaseNumber" min="0" max="10" step="0.01"' in _HTML
    assert "function syncChannelRelease(channel)" in _JS
    assert "function bindChannelRelease()" in _JS
    assert "applyPatch(partPatch(part, { release_s: value }), true)" in _JS
    assert "event.release_s === undefined ? performance.release_s : event.release_s" in _JS


def test_track_attack_and_hard_stop_are_optional_track_only_controls():
    assert '<label for="channelAttackRange">Track Attack</label>' in _HTML
    assert 'id="channelAttackEnabled"' in _HTML
    assert 'id="channelAttackRange" min="10" max="5000"' in _HTML
    assert 'including Automatic instruments.' in _HTML
    assert "function syncChannelAttack(channel)" in _JS
    assert "function bindChannelAttack()" in _JS
    assert "partPatch(part, { attack_ms: value })" in _JS
    assert "id=\"channelHardStopEnabled\"" in _HTML
    assert "id=\"channelHardStop\"" in _HTML
    assert "function syncChannelHardStop(channel)" in _JS
    assert "function bindChannelHardStop()" in _JS
    assert "partPatch(part, { hard_stop: value })" in _JS


def test_conversion_toolbar_button_toggles_its_inspector():
    assert "function toggleInspector()" in _JS
    assert "el('conversionBtn').addEventListener('click', toggleInspector)" in _JS


def test_dense_roll_rendering_is_indexed_cached_and_level_of_detail_aware():
    assert "prefixEnds" in _JS
    assert "function lowerBound(values, target)" in _JS
    assert "function upperBoundRecords(records, target)" in _JS
    assert "function visibleRenderEvents(scrollLeft, scrollTop, width, height)" in _JS
    assert "recordsOverlapping(index.buckets[127 - row]" in _JS
    assert "var OVERVIEW_CACHE_PIXEL_BUDGET = 16000000" in _JS
    assert "function canCacheOverview()" in _JS
    assert "RENDER.overviewValid && RENDER.overviewCanvas" in _JS
    assert "context.drawImage(" in _JS
    assert "var detailed = ROLL.rowHeight >= 12 && ROLL.zoom > 140" in _JS
    assert "batch.blocks.forEach(function (geometry)" in _JS
    assert "context.rect(geometry.x, geometry.y, geometry.width, geometry.height)" in _JS


def test_rendering_caps_pixel_cost_and_throttles_nonvisual_transport_updates():
    assert "var MAX_CANVAS_PIXEL_RATIO = 2" in _JS
    assert "Math.ceil(viewportWidth / Math.max(1, minimumPixels)) + 2" in _JS
    assert "markerAt(tempoRenderIndex(), tick, 'tick')" in _JS
    assert "markerAt(tempoRenderIndex(), timeMs, 'time_ms')" in _JS
    assert "RENDER.lineTimingSource === timing" in _JS
    assert "RENDER.transportTenth !== tenth" in _JS
    assert "now - RENDER.scrubberPaintAt >= 33" in _JS


def test_global_preview_uses_direct_song_scoped_audio_without_setup_extraction():
    assert 'id="audioBanner"' in _HTML
    assert 'id="slotAudio"' not in _HTML
    assert "el('audioText')" not in _JS
    assert "api().audio_status(" in _JS
    assert "api().extract_audio(" not in _JS
    assert "api().preview_samples(missing)" in _JS
    assert "requiredAudioNames()" in _JS
    assert "retainRequiredBuffers()" in _JS
    assert "AUDIO.unavailable[name] = true" in _JS
    assert (
        "Song preview skips those events; exported maps still use their exact event strings." in _JS
    )
    assert "invalidateAudio(true)" in _JS, "a different song cannot reuse prior buffers"
    assert "refreshAudioAfterSettings()" in _JS
    assert "AUDIO.performance = capturePlaybackPreview()" in _JS
    assert "prepareSongAudio();" in _JS
    assert re.search(
        r"function refreshAudio\(\).*?pausePlayback\(\).*?api\(\)\.audio_status\(\)"
        r".*?invalidateAudio\(true\)",
        _JS,
        re.DOTALL,
    ), "refresh must stop transport and discard buffers from the previous source"
    assert "api().preview_manifest(" not in _JS, "startup already carries the manifest"


def test_settings_edits_handoff_without_stopping_transport():
    apply_body = re.search(
        r"function applyPatch\(body, _resumePlayback\) \{(?P<body>.*?)\n  \}",
        _JS,
        re.DOTALL,
    )
    assert apply_body
    assert "pausePlayback()" not in apply_body.group("body")
    assert "function capturePlaybackPreview()" in _JS
    assert "function playbackEvents()" in _JS
    assert "function handoffPlaybackPreview()" in _JS
    assert "AUDIO.scheduledThrough = horizon" in _JS
    assert "AUDIO.nextIndex = firstFutureEvent(boundary + 0.001)" in _JS


def test_header_commands_are_conventional_desktop_menus():
    for label in ("File", "Playback", "Options", "View"):
        assert ">%s</button>" % label in _HTML
    for shortcut in ("Ctrl+I", "Ctrl+E", "Ctrl+R", "Ctrl+,", "Space", "Home"):
        assert shortcut in _HTML


def test_conversion_limits_stay_in_a_nonblocking_inspector():
    assert 'id="conversionInspector"' in _HTML
    for control in (
        "maxSpeakersRange",
        "maxPolyRange",
        "releaseRange",
        "hardStop",
        "sustainRange",
        "bassRange",
        "bassPitchNumber",
        "familyBehavior",
        "restoreDefaults",
    ):
        assert 'id="%s"' % control in _HTML
    assert "api().reset_tuning(" in _JS


def test_warnings_live_in_the_bottom_control_plane_and_notification_inspector():
    for control in (
        "controlPlane",
        "notificationsBtn",
        "notificationBadge",
        "notificationsInspector",
        "notificationsSummary",
        "notificationList",
        "closeNotifications",
    ):
        assert 'id="%s"' % control in _HTML
    assert 'role="toolbar"' in _HTML
    assert "warnBar" not in _HTML
    assert "warnBar" not in _JS
    assert "warnbar" not in _CSS
    assert "warnings.forEach(function (message)" in _JS
    assert "warnings[0]" not in _JS
    assert ".transport-play, .control-button" in _CSS
    assert re.search(r"function openInspector\(\)\s*\{\s*closeNotifications\(\);", _JS)
    assert re.search(r"function openNotifications\(\)\s*\{\s*closeInspector\(\);", _JS)
    assert "else if (NOTIFICATIONS_OPEN) { closeNotifications(); }" in _JS
    assert "el('notificationsBtn').addEventListener('click', toggleNotifications)" in _JS
    assert re.search(
        r"\.notification-row\s*\{[^}]*border-bottom:\s*1px solid var\(--border\)",
        _CSS,
    )


def test_the_window_s_assets_are_declared_against_the_ui_package():
    """The wheel has to carry `web/`, and there is one spelling that does it.

    Declared against the `snapmap_midi.ui` package with a `web/` pattern, not as
    a `ui/web/*` glob under `snapmap_midi`. The glob form reaches through a
    directory that is itself a declared package, which setuptools does not
    reliably honour, and the failure mode is silent in the worst way: the wheel
    builds, installs, imports, and opens a window with no markup in it. A blank
    page, no error, on a machine that installed rather than cloned -- so it
    cannot happen here, where the folder is always on disk.
    """
    package_data = _pyproject()["tool"]["setuptools"]["package-data"]
    patterns = package_data["snapmap_midi.ui"]
    assert any(p.startswith("web/") for p in patterns), patterns
    assert not any(p.startswith("ui/") for p in package_data["snapmap_midi"]), (
        "the window's assets are declared as a glob under snapmap_midi; spell them against "
        "the snapmap_midi.ui package instead"
    )
    assert (_WEB / "index.html").is_file()


def test_every_statistic_the_window_prints_is_one_a_compile_produces():
    """`stats` crosses the bridge as a dictionary and is read by key in Javascript.

    A key that no longer exists reads as `undefined`, and every one of these
    sites already coalesces -- `stats.notes || 0` -- because a missing statistic
    must not blank the status bar. So a renamed key does not fail: it prints
    zero. A window that confidently reports 0 long sustains for an arrangement
    full of them is worse than one that reports nothing, and nothing else in
    this suite is looking at both sides of that name.

    The Python side is a real compile of a real file rather than a list written
    out here. A list would be a third copy of these names and would go stale in
    the same silence as the second.
    """
    produced = set(Session(midi=_TINY_MIDI).stats())
    read = set(re.findall(r"\bstats\.([a-z_]+)", _JS))
    assert read, "no `stats.<key>` reads found in app.js -- this test stopped looking"
    assert read <= produced, "app.js reads statistics no compile produces: %s" % sorted(
        read - produced
    )


def test_every_setting_the_window_reads_is_one_the_document_holds():
    """Same seam, other direction: the document's own top-level keys.

    These fail more quietly than the statistics do. `settings.out_dir` gone
    missing leaves the Output folder field empty, which is exactly what an unset
    output folder looks like -- so the window reports the default destination
    while the session is holding a different one, and the first anybody hears of
    it is a map that landed somewhere they did not choose.

    Read off `defaults()` rather than listed, so adding a key to the document is
    enough and removing one is caught.
    """
    produced = set(settings_module.defaults())
    read = set(re.findall(r"\bsettings\.([a-z_]+)", _JS))
    assert read, "no `settings.<key>` reads found in app.js -- this test stopped looking"
    assert read <= produced, "app.js reads settings the document does not have: %s" % sorted(
        read - produced
    )


def test_the_part_panel_can_say_a_part_is_a_kit():
    """The mode exists in the document and the parser already obeys it, but a
    setting with no control is a setting nobody has. Percussion off channel 10
    is ordinary -- a composer who put the kit on channel 6 hears it played as a
    piano, and nothing in the window says why or offers a way out.
    """
    assert 'id="channelPercussion"' in _HTML
    assert 'id="channelPercussionHelp"' in _HTML
    for mode in ("auto", "kit", "melodic"):
        assert '<option value="%s">' % mode in _HTML
    assert "function syncChannelPercussion(channel)" in _JS
    assert 'partPatch(channel, { percussion: this.value })' in _JS


def test_the_part_panel_lists_the_keys_a_kit_plays():
    """`drum_keys` was reachable only by hand-editing the sidecar, so the answer
    to "I do not like this kick" was "edit JSON". Worse, a key General MIDI
    names but `DRUM_MAP` does not map plays NOTHING, and silence is
    indistinguishable from a working kit until the map is in game.
    """
    assert 'id="drumKeysGroup"' in _HTML
    assert 'id="drumKeyList"' in _HTML
    assert 'id="drumKeysCount"' in _HTML
    assert "function renderDrumKeys(channel)" in _JS
    assert "function openDrumKeyBrowser(partKey, key)" in _JS
    assert ".drum-key-silent" in _CSS
    assert ".drum-key-row" in _CSS


def test_a_drum_key_patch_carries_every_other_key_with_it():
    """`drum_keys` replaces wholesale -- that asymmetry is what makes removal
    expressible, and it is also what makes a patch of one entry erase the rest.
    Choosing a snare must not silently drop the kick chosen a minute earlier.
    """
    body = re.search(r"function withKey\(table, key, sound\) \{(.+?)\n  \}", _JS, re.S)
    assert body, "withKey is gone or was renamed"
    body = body.group(1)
    assert "Object.keys(table).forEach" in body, "the patch no longer copies the map"
    assert "delete next[String(key)]" in body, "no way left to take a choice back off"
    # Both tables are written through it -- the song's and the user's -- so a
    # regression in either one shows up here.
    assert "drum_keys: withKey(drumKeyOverrides(), key, sound)" in _JS
    assert "set_drum_defaults(withKey(drumDefaults(), key, sound))" in _JS


def test_the_key_picker_offers_only_sounds_the_document_will_accept():
    """The full browser lists every installed event, and `_drum_keys` refuses
    all but the percussion pool: a pitched sound holds one fixed note under
    every hit, and a looping ambience is never stopped. Offering a choice the
    document rejects turns a click into an error toast.
    """
    assert "function filteredDrumSounds()" in _JS
    assert "drumPool()" in _JS
    assert "STATE.catalog && STATE.catalog.drum_sounds" in _JS
    # And the way back to the table's own answer is always the first row, never
    # filtered away by a search: undoing a choice is not a search result.
    assert 'list.appendChild(resultRow(\n      "automatic", ""' in _JS


def test_the_key_picker_says_where_the_choice_is_being_saved():
    """One picker writes two different tables. Without the scope on screen the
    same click means "this song" or "every song I ever open" and nothing says
    which -- and the second one is not undoable by closing the file.
    """
    assert 'id="soundScope"' in _HTML
    assert 'id="soundScopeField"' in _HTML
    assert '<option value="song">' in _HTML
    assert '<option value="default">' in _HTML
    assert "function drumScope()" in _JS
    # The verb has to move with it, because the button is the last thing read
    # before the click that cannot be taken back by closing the song.
    assert '"Save as my default"' in _JS
    assert '"Use for this song"' in _JS
    # And the scope field is only up while a drum key is being chosen: it means
    # nothing for a whole part's instrument.
    assert 'el("soundScopeField").hidden = false;' in _JS
    assert 'el("soundScopeField").hidden = true;' in _JS


def test_saving_a_default_drops_the_song_choice_for_that_key():
    """The song wins over a default by design. Saving a default for a key the
    song is already overriding would store the choice and change nothing
    audible, which reads exactly like a failed save.
    """
    body = re.search(r"function setDrumKeyDefault\(key, sound\) \{(.+?)\n  \}\n", _JS, re.S)
    assert body, "setDrumKeyDefault is gone or was renamed"
    body = body.group(1)
    assert "withKey(drumKeyOverrides(), key, null)" in body
    assert "set_drum_defaults(" in body


def test_a_drum_key_row_says_which_table_answered_for_it():
    """Three tables answer for a key. A row that showed the sound but not its
    origin makes "save as my default" look like a no-op on the keys the song
    already claims."""
    assert 'choice.scope === "song" ? "this song" : "your default"' in _JS
    assert 'STATE.drum_defaults' in _JS
    assert 'STATE.catalog && STATE.catalog.drum_shipped' in _JS
    # The redraw payload has to carry it, or the badge is stale the moment a
    # default is saved.
    assert "'drum_defaults'" in _JS


def test_the_key_picker_draws_on_the_percussive_folders_as_well():
    """Seventy curated sounds could not cover a kit anyone wanted. The folders
    are where the game says what a sound is FOR -- impacts, footsteps, foley,
    the interface branch -- which is the only signal that survives contact with
    a catalog where a half-second event is as likely to be a scope chirp.
    """
    assert "function eventIsDrummable(event)" in _JS
    assert "function drumChoices()" in _JS
    assert "STATE.catalog && STATE.catalog.drum_folders" in _JS
    # Both halves of the rule. Dropping either one is silent: without the
    # folder check the picker fills with weapon chirps, and without the loop
    # check it offers sounds that hold an emitter open forever.
    assert 'event.looping !== false || event.looping_known !== true' in _JS
    assert 'path.indexOf(folder + "/") === 0' in _JS


def test_the_curated_percussion_stays_at_the_top_of_the_picker():
    """The curated names carry hand-written ear-labels, and this game's names
    lie: `play_noise_tom` is a knock on a door. Sorting them in with five
    hundred catalog events would bury the ones that describe themselves."""
    assert "if (!!curated[left] !== !!curated[right]) { return curated[left] ? -1 : 1; }" in _JS
    assert '"Curated percussion"' in _JS


def test_a_drum_sound_row_leads_with_its_length():
    """Length is what decides whether a sound works as a hit at all. A
    three-second sample on a sixteenth-note hat leaks nothing -- it just piles
    up voices and turns to mush -- so it has to be visible before the click,
    not discovered after an export."""
    assert 'var metadata = [event ? eventDuration(event) : "", entry.group];' in _JS


def test_global_and_track_voice_controls_are_both_exposed():
    """Global Voices caps the map; Track Voices budgets one part within it."""
    assert '<label for="maxSpeakersRange">Global Voices</label>' in _HTML
    assert '<span class="hint">entire song</span>' in _HTML
    assert 'id="maxSpeakersRange" min="1" max="128" value="32"' in _HTML
    assert 'id="maxSpeakersNumber" min="1" max="128" value="32"' in _HTML
    assert '<label for="songPolyphonyRange">Global Polyphony</label>' in _HTML
    assert 'id="songPolyphonyRange" min="1" max="128" value="32"' in _HTML
    assert 'id="songPolyphonyNumber" min="1" max="128" value="32"' in _HTML
    assert "including notes layered on the shared emitter" in _HTML
    assert "Ringing sample tails do not consume this limit" in _HTML
    assert "bindPair('songPolyphonyRange', 'songPolyphonyNumber', 'song_polyphony'" in _JS
    assert (
        "Sets the maximum number of dedicated sounds the whole song can play at once."
        in _HTML
    )
    assert '<label for="channelVoicesRange">Track Voices</label>' in _HTML
    assert 'id="channelVoicesRange" min="1" max="128"' in _HTML
    assert "Caps how many Global Voices this track can use." in _HTML
    assert "Extra low notes are muted and shown as dashed outlines" in _HTML
    assert '<label for="polyEnabled">Default Track Polyphony</label>' in _HTML
    assert (
        "Sets the polyphony limit used by every track unless that track has its own setting."
        in _HTML
    )
    assert '<label for="channelPolyRange">Track Polyphony</label>' in _HTML
    assert '<label for="sustainEnabled">Default Track Sustain Limit</label>' in _HTML
    assert '<label for="channelSustainRange">Track Sustain Limit</label>' in _HTML
    assert 'id="channelSustainEnabled"' in _HTML
    assert 'id="channelSustainRange" min="50" max="5000"' in _HTML
    assert "It does not change how many voices the track can use." in _HTML
    assert 'function syncChannelVoices(channel)' in _JS
    assert 'function syncChannelSustain(channel)' in _JS
    assert 'bindChannelLimit("voices", "max_speakers"' in _JS
    assert 'bindChannelLimit("sustain_ms", "cap_sustain_ms"' in _JS
    assert '<label for="channelGlideRange">Track glide</label>' in _HTML
    assert 'id="channelGlideRange" min="0" max="5000" value="0"' in _HTML
    assert 'id="channelGlideNumber" min="0" max="5000" value="0"' in _HTML
    assert "Default: No glide (0 ms)." in _HTML
    assert "Track Voices 1 gives monophonic portamento." in _HTML
