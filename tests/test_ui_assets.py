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
        ".win-controls { display:flex; margin-left:8px; }",
        (
            ".win-btn { width:30px; height:30px; display:flex; align-items:center; "
            "justify-content:center; color:var(--muted); font-size:12px; cursor:default; }"
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
    symbols = set(re.findall(r'<symbol id="icon-([a-z-]+)"', _HTML))
    assert symbols == {
        "circle-alert",
        "copy",
        "minus",
        "pause",
        "play",
        "square",
        "triangle-alert",
        "x",
    }
    assert "lucide.min.js" not in _HTML
    assert "unpkg.com" not in _HTML
    for control in ("winMin", "winMax", "winClose", "transportPlay"):
        assert re.search(r'id="%s"[^>]*>.*?class="ui-icon"' % control, _HTML)
    assert "setIcon(el('winMax'), maximized ? 'copy' : 'square')" in _JS
    assert "setIcon(el('playGlyph'), AUDIO.playing ? 'pause' : 'play')" in _JS
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
    assert "preview_sound" not in _JS


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
    assert re.search(r"fillNoteBlock\(\s*context,\s*startX,\s*eventY,\s*eventWidth,", _JS)
    assert "context.fillRect(startX, eventY" not in _JS
    assert "context.imageSmoothingQuality = 'high'" in _JS
    assert "context.fontKerning = 'normal'" in _JS
    assert "context.textRendering = 'geometricPrecision'" in _JS
    assert "context.font = '600 ' + labelSize + 'px \"Segoe UI\"" in _JS
    assert "context.measureText(label).width <= eventWidth - 8" in _JS


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
    assert re.search(
        r"\.roll-pane::after\s*\{[^}]*top:\s*0;[^}]*left:\s*72px;[^}]*right:\s*0;"
        r"[^}]*height:\s*31px;[^}]*border-bottom:\s*1px solid var\(--border2\)",
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
    assert "var locked = AUDIO.playing && height > 0" in _JS
    assert "lock.style.right = width + 'px'" in _JS
    assert re.search(
        r"\.horizontal-scroll-lock\s*\{[^}]*position:\s*absolute;[^}]*z-index:\s*6;"
        r"[^}]*left:\s*72px;[^}]*bottom:\s*0;[^}]*background:\s*var\(--scrollDisabled\);"
        r"[^}]*cursor:\s*default;[^}]*pointer-events:\s*auto",
        _CSS,
    )


def test_playback_coalesces_scroll_redraws_and_preserves_vertical_wheel_input():
    assert "var DRAW_FRAME = null" in _JS
    assert "cancelAnimationFrame(DRAW_FRAME)" in _JS
    assert "DRAW_FRAME = requestAnimationFrame(function ()" in _JS
    assert "function handleRollScroll()" in _JS
    assert "if (!AUDIO.playing) { queueDraw(); }" in _JS
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
    for control in ("gridResolution", "timeSignature", "rollZoom", "rollZoomValue"):
        assert 'id="%s"' % control in _HTML
    for resolution in ("1", "2", "4", "8", "16", "32"):
        assert 'option value="%s"' % resolution in _HTML
    for meter in ("2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "9/8", "12/8"):
        assert 'option value="%s"' % meter in _HTML
    assert 'id="rollZoom" min="0" max="60"' in _HTML
    assert "ticksPerBeat * 4 / ROLL.gridDenominator" in _JS
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
    assert "var anchor = ROLL.viewportWidth * 0.32" in _JS
    assert "viewport.scrollLeft = clamp(x - anchor" in _JS
    assert "ROLL.contentWidth - ROLL.viewportWidth" in _JS
    assert "function contentXAtTime(timeMs)" in _JS
    assert "var startX = contentXAtTime(eventStart)" in _JS
    assert "var playheadX = contentXAtTime(position)" in _JS
    assert "function audibleContextTime()" in _JS
    assert "AUDIO.context.getOutputTimestamp()" in _JS
    assert "audibleContextTime() - AUDIO.anchorTime" in _JS


def test_playback_and_hover_glow_use_the_same_note_geometry_as_the_playhead():
    position = (
        "var position = positionOverride === undefined ? currentPosition() : positionOverride"
    )
    active = "var active = AUDIO.playing && position >= eventStart && position < eventEnd"
    playhead = "var playheadX = contentXAtTime(position) - viewport.scrollLeft"
    assert position in _JS
    assert active in _JS
    assert playhead in _JS
    assert _JS.index(position) < _JS.index(active) < _JS.index(playhead)
    assert "var glowing = active || hovered" in _JS
    assert "context.shadowColor = color" in _JS
    assert "context.shadowBlur = 7" in _JS
    assert "context.globalAlpha = 0.16" in _JS
    assert "var hoverPoint = !AUDIO.playing && !SEEK_DRAG ? pianoRollPointer(canvas) : null" in _JS
    assert "hoverPoint.x >= startX && hoverPoint.x <= startX + eventWidth" in _JS
    assert "hoverPoint.y >= eventY && hoverPoint.y <= eventY + eventHeight" in _JS
    assert "canvas.addEventListener('pointermove', updateNotePointer)" in _JS
    assert "canvas.addEventListener('pointerleave', clearNotePointer)" in _JS


def test_global_preview_is_wired_to_explicit_local_audio_setup():
    assert 'id="audioBanner"' in _HTML
    assert 'id="slotAudio"' in _HTML
    assert "api().extract_audio(" in _JS
    assert "api().preview_samples(" in _JS
    assert "api().preview_manifest(" not in _JS, "startup already carries the manifest"


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
