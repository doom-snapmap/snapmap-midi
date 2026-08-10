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

import re
import tomllib
from pathlib import Path

from snapmap_midi import settings as settings_module
from snapmap_midi.ui.api import Bridge
from snapmap_midi.ui.app import web_root
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
    """Relative paths, because the window is loaded off the filesystem by path.

    Nothing is served: `webview.create_window` is handed `index.html` and the
    engine resolves the two links against it. A link that no longer matches the
    file beside it does not raise -- the page renders unstyled and inert, which
    reads as the window having failed to load its data rather than its assets.
    """
    assert 'href="styles.css"' in _HTML
    assert 'src="app.js"' in _HTML


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


def test_reduced_motion_turns_the_ruler_s_animation_off():
    """The ruler's instrument track slides on every family change.

    That transition is the one piece of motion in the window and it is on the
    control somebody changes repeatedly, so for a reader who has asked their
    system for less of it this is precisely the thing they asked about. The
    preference is a system setting; honouring it is not a preference.
    """
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
