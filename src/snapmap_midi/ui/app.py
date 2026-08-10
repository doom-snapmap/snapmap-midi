"""Opening the MIDI workstation, and failing usefully when it will not open.

pywebview is the whole of the window. It hosts the markup under `web/` in the
platform's own browser engine and hands the bridge to Javascript as
`window.pywebview.api`. Nothing is served and nothing listens: the markup is
loaded through a `file:///` URI, so the window has no address and no port and
cannot be reached from anywhere but this process.

Every import it needs happens inside `run` rather than at the top of the
module. pywebview is declared for Windows only, and the bridge reaches the
whole library through it; at module scope either one would make importing this
package -- which `snapmap-midi compile` does not need at all -- fail on a
machine that is never going to open a window.
"""

from __future__ import annotations

from pathlib import Path

#: The title bar. Named for the command, because that is what the user typed to
#: get here and what they will look for in a task switcher afterwards.
TITLE = "snapmap-midi"

#: Room for sixteen channel rows and a ruler each without scrolling, which is
#: what makes the window readable as one picture of the song rather than a form
#: to page through.
WIDTH = 1180
HEIGHT = 820

#: The ruler places notes as percentages of a shared 0-127 axis, so its cells
#: are a fraction of the panel wide. Below this the semitones overlap into one
#: solid block and the density strip stops carrying the information it exists
#: for, so the window refuses to be dragged smaller rather than degrading into
#: a bar that means nothing.
MIN_SIZE = (960, 640)


def web_root() -> Path:
    """The folder holding the window's markup, style and behaviour.

    Resolved from this module's own file rather than the working directory. A
    console script runs from wherever the user happens to be standing, and a
    relative path would open a blank window everywhere but one directory --
    with no error, because a browser engine handed a missing file renders an
    empty page perfectly happily.
    """
    return Path(__file__).resolve().parent / "web"


def web_url() -> str:
    """The local entry point as a file URI, not a path pywebview will serve.

    pywebview treats a plain local path as a request to start a Bottle server
    on a random loopback port. An explicit `file:///` URI goes straight to
    WebView2 instead, preserves the relative CSS and Javascript links, and
    keeps the window true to its no-listener security contract.
    """
    return (web_root() / "index.html").as_uri()


def run(midi=None, settings=None) -> int:
    """Open the window and return the exit code the command line should use.

    Two ways this fails and they are not the same failure, which is why they
    are caught separately and say different things:

    pywebview absent is a package that was never installed, and the fix is one
    pip command. The dependency is declared for Windows only, so off Windows
    this message is the entire experience of the feature and has to name that
    command rather than describe the problem.

    pywebview present but the Edge WebView2 runtime absent imports perfectly
    cleanly and fails at `start()` instead -- a different install, a different
    sentence, and the more likely of the two on a fresh Windows machine. An
    earlier draft caught only the first, so this one arrived as a bare stack
    trace at a person who had to be told to tick "Add python.exe to PATH".
    """
    try:
        import webview
    except ImportError:
        print("the MIDI workstation needs pywebview, which is not installed")
        print('  pip install "snapmap-midi[ui]"')
        return 2

    from snapmap_midi.ui.api import Bridge
    from snapmap_midi.ui.chrome import WindowChrome

    bridge = Bridge(midi=midi, settings_path=settings)
    # An ORDINARY window, and then the frame comes off it -- see `ui/chrome.py`.
    # `frameless=True` here would be one argument instead of two lines and it is
    # measurably the wrong one: it drops WS_THICKFRAME, WS_SYSMENU and
    # WS_MINIMIZEBOX, so the window cannot be resized, cannot be minimised from
    # its own taskbar button, has no Aero Snap, and covers the taskbar when
    # maximised.
    window = webview.create_window(
        TITLE,
        web_url(),
        js_api=bridge,
        width=WIDTH,
        height=HEIGHT,
        min_size=MIN_SIZE,
    )
    # Handed over after the fact because neither can be built first: the window
    # is created WITH the bridge as its Javascript surface, and the bridge needs
    # the window to hang a native file dialog on. Until this line the bridge's
    # pickers report that there is nothing to open a dialog on, which is also
    # how they stay testable with no browser engine present.
    bridge.attach(window)
    # Handed over the same way and for the same reason. The chrome installs
    # itself on the window's `shown` event, so this line only has to happen
    # before `start()`; what it buys is the page being able to drag, resize,
    # minimise, maximise and close a window that no longer has a title bar to do
    # any of that with.
    bridge.attach_chrome(WindowChrome(window))

    try:
        webview.start()
    except Exception as exc:
        print("the MIDI workstation could not open (%s)" % exc)
        print("  install the Microsoft Edge WebView2 runtime, then try again")
        return 2
    return 0
