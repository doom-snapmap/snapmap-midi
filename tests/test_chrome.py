"""The window frame, proven without ever opening a window.

Nothing here creates a window, imports pywebview, or calls Win32. That is not
convenience -- it is the only way this code gets tested at all. The border
bookkeeping runs on pywebview's UI-thread `before_show` event and the native
frame is installed from its worker-thread `shown` event, where pywebview
swallows exceptions into a log record and Windows answers a mistake by ending
the process with no traceback. A suite that needed a real window to reach any
of it would test none of it.

So the module talks to Win32 through one small facade, and these tests replace
that facade with a recorder. What is left to check is exactly what went wrong
while this was being written: the message arithmetic, the styles that have to
survive, the reference that must not be collected, and the private name on the
bridge.

That last one is the sharpest. pywebview builds `window.pywebview.api` by
walking every PUBLIC non-callable attribute of the bridge and recursing into
each one carrying a `__module__` (`webview/util.py`, `get_functions`). Park a
window or a chrome on a public name and it walks the native form's
accessibility tree until the stack ends -- inside the injection, so
`pywebviewready` never fires and the window renders nothing, forever, with no
error. `test_pywebview_can_walk_the_bridge_without_falling_in` mirrors that
rule exactly rather than asserting a list of names, because the rule is what
the failure obeys.
"""

from __future__ import annotations

import ctypes
import inspect

import pytest

from snapmap_midi.ui import chrome as chrome_module
from snapmap_midi.ui.api import Bridge
from snapmap_midi.ui.chrome import WindowChrome

#: A handle wider than 32 bits. Anything that truncates one is holding a
#: pointer into somebody else's memory, and the fake below stores it verbatim so
#: an accidental narrowing shows up as an unequal assertion rather than a crash.
HWND = 0x0000_02F4_1A2B_3C4D

#: The window procedure already on the window when the chrome arrives.
OLD_PROC = 0x0000_7FF6_0000_1234

#: What the fake answers a forwarded message with, so a test can tell
#: "forwarded" apart from "handled and returned zero".
FORWARDED = 0x5A5A

#: Deliberately three different numbers: the horizontal inset must come from
#: SM_CXFRAME and the vertical from SM_CYFRAME, and equal metrics would let a
#: swapped axis pass.
METRICS = {
    chrome_module.SM_CXFRAME: 4,
    chrome_module.SM_CYFRAME: 5,
    chrome_module.SM_CXPADDEDBORDER: 3,
}
FRAME_X = 4 + 3
FRAME_Y = 5 + 3

#: The style pywebview leaves behind for `frameless=True`, measured on 6.2.1.
#: Used as the starting point so the assertion about what gets re-added is made
#: against the real hole rather than against zero.
FRAMELESS_STYLE = 0x16010000


class _Event:
    """pywebview's `Event`, reduced to the one thing this module uses: `+=`."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _Events:
    def __init__(self):
        self.before_show = _Event()
        self.shown = _Event()


class _Handle:
    def __init__(self, value):
        self._value = value

    def ToInt64(self):
        return self._value


class _Native:
    """The WinForms form, reduced to the handle the chrome reads off it."""

    def __init__(self, value):
        self.Handle = _Handle(value)


class _Window:
    def __init__(self, handle=HWND, native=True):
        self.native = _Native(handle) if native else None
        self.events = _Events()
        self.destroyed = 0

    def destroy(self):
        self.destroyed += 1


class _FakeWin32:
    """Records what the chrome asked Win32 for, and answers none of it for real."""

    def __init__(self, zoomed=False, style=FRAMELESS_STYLE):
        self.zoomed = zoomed
        self.style = style
        self.metrics = dict(METRICS)
        self.shown = []
        self.loops = []
        self.loop_requests = []
        self.refreshed = []
        self.margin = None
        self.installed = None
        self.forwarded = []

    def system_metric(self, index):
        return self.metrics[index]

    def wrap_proc(self, function):
        # The real one returns a ctypes trampoline. Handing the function back
        # unchanged is what lets a test call the installed procedure directly.
        return function

    def window_proc(self, hwnd):
        return OLD_PROC

    def set_window_proc(self, hwnd, proc):
        self.installed = proc

    def call_window_proc(self, proc, hwnd, message, wparam, lparam):
        self.forwarded.append((proc, hwnd, message, wparam, lparam))
        return FORWARDED

    def window_style(self, hwnd):
        return self.style

    def set_window_style(self, hwnd, style):
        self.style = style

    def is_zoomed(self, hwnd):
        return self.zoomed

    def show_window(self, hwnd, command):
        self.shown.append((hwnd, command))

    def refresh_frame(self, hwnd):
        self.refreshed.append(hwnd)

    def extend_frame(self, hwnd, margin):
        self.margin = margin

    def start_native_loop(self, hwnd, code):
        self.loops.append((hwnd, code))

    def request_native_loop(self, hwnd, code):
        self.loop_requests.append((hwnd, code))
        return True


def _chrome(monkeypatch, install=True, **kwargs):
    """A chrome on a fake window, installed the way pywebview installs it."""
    api = _FakeWin32(**kwargs)
    monkeypatch.setattr(chrome_module, "_win32", lambda: api)
    window = _Window()
    chrome = WindowChrome(window)
    if install:
        window.events.before_show.handlers[0](window)
        window.events.shown.handlers[0](window)
    return chrome, api, window


def _rect():
    """A proposed client rectangle in real memory, and its address."""
    params = chrome_module.NCCALCSIZE_PARAMS()
    params.rgrc[0].left = 100
    params.rgrc[0].top = 200
    params.rgrc[0].right = 900
    params.rgrc[0].bottom = 700
    return params, ctypes.addressof(params)


# ---- installation ----


def test_form_bookkeeping_and_native_frame_use_their_safe_events(monkeypatch):
    """WinForms must be changed on its UI thread, while subclassing must wait
    until the form has settled. Reversing either half has produced the same
    blank, non-responsive window for a different reason."""
    api = _FakeWin32()
    monkeypatch.setattr(chrome_module, "_win32", lambda: api)
    monkeypatch.setattr(chrome_module, "supported", lambda: True)
    prepared = []
    monkeypatch.setattr(
        chrome_module,
        "tell_the_form_its_frame_is_gone",
        lambda native: prepared.append(native) or True,
    )
    window = _Window()
    chrome = WindowChrome(window)
    assert len(window.events.shown.handlers) == 1
    assert len(window.events.before_show.handlers) == 1

    window.events.before_show.handlers[0](window)
    assert prepared == [window.native]
    assert chrome.hwnd == 0
    assert api.installed is None

    window.events.shown.handlers[0](window)
    assert chrome.hwnd == HWND
    assert api.installed is chrome._proc_ref


def test_installing_re_adds_every_style_a_managed_window_needs(monkeypatch):
    """The point of the whole module. `frameless=True` leaves 0x16010000 -- no
    resize border, no system menu, no minimise -- and this puts all four back,
    because what is being removed is the DRAWING of the frame and never the
    behaviour behind it."""
    _, api, _ = _chrome(monkeypatch)
    assert api.style & chrome_module.WS_THICKFRAME
    assert api.style & chrome_module.WS_MINIMIZEBOX
    assert api.style & chrome_module.WS_MAXIMIZEBOX
    assert api.style & chrome_module.WS_SYSMENU
    assert api.style == FRAMELESS_STYLE | chrome_module.MANAGED_STYLES


def test_the_window_procedure_is_kept_alive_by_the_chrome(monkeypatch):
    """The trampoline Windows jumps to is created here and referenced by
    nothing on the Win32 side. Collected, the next message reaches freed memory
    and the process disappears -- no traceback, no exit message, no clue."""
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome._proc_ref is not None
    assert chrome._proc_ref is api.installed
    assert chrome._old_proc == OLD_PROC


def test_the_shadow_is_one_pixel_of_frame_and_not_none(monkeypatch):
    """That single pixel is the whole of what makes the compositor draw a drop
    shadow and Windows 11 rounded corners on a window with no caption. At zero
    the window reads as a flat rectangle pasted onto the desktop."""
    _, api, _ = _chrome(monkeypatch)
    assert api.margin == 1


def test_the_frame_is_recalculated_immediately(monkeypatch):
    """Without it the caption lingers until the first move or resize, so the
    window opens showing the very header this exists to remove and then loses it
    under the user's hand."""
    _, api, _ = _chrome(monkeypatch)
    assert api.refreshed == [HWND]


def test_a_window_with_no_native_form_yet_installs_nothing(monkeypatch):
    api = _FakeWin32()
    monkeypatch.setattr(chrome_module, "_win32", lambda: api)
    window = _Window(native=False)
    chrome = WindowChrome(window)
    window.events.shown.handlers[0](window)
    assert chrome.hwnd == 0
    assert api.installed is None


def test_installing_off_windows_is_a_window_with_a_title_bar(monkeypatch):
    """Not an exception. pywebview runs `shown` handlers on a worker thread and
    logs whatever they raise, so raising here would be silent anyway -- and a
    window that kept its caption is a cosmetic loss, not a reason to fail to
    open."""
    api = _FakeWin32()
    monkeypatch.setattr(chrome_module, "_win32", lambda: api)
    monkeypatch.setattr(chrome_module, "supported", lambda: False)
    window = _Window()
    chrome = WindowChrome(window)
    window.events.shown.handlers[0](window)
    assert chrome.hwnd == 0
    assert api.installed is None


# ---- the messages ----


def test_nccalcsize_consumes_the_whole_non_client_area(monkeypatch):
    """Returning zero with the rectangle untouched is what makes the client
    equal the window: no caption strip, no border inset, nothing left for the
    system to draw a title bar in."""
    chrome, _, _ = _chrome(monkeypatch)
    params, address = _rect()
    result = chrome._proc_ref(HWND, chrome_module.WM_NCCALCSIZE, 1, address)
    assert result == 0
    assert (params.rgrc[0].left, params.rgrc[0].top) == (100, 200)
    assert (params.rgrc[0].right, params.rgrc[0].bottom) == (900, 700)


def test_a_maximized_window_gives_the_resize_frame_back(monkeypatch):
    """Maximised, Windows pushes the window a resize frame past the work area on
    every side. A client spanning the whole window then hangs off the monitor
    and covers the taskbar, which is exactly what `frameless=True` does."""
    chrome, _, _ = _chrome(monkeypatch, zoomed=True)
    params, address = _rect()
    assert chrome._proc_ref(HWND, chrome_module.WM_NCCALCSIZE, 1, address) == 0
    assert params.rgrc[0].left == 100 + FRAME_X
    assert params.rgrc[0].right == 900 - FRAME_X
    assert params.rgrc[0].top == 200 + FRAME_Y
    assert params.rgrc[0].bottom == 700 - FRAME_Y


def test_nccalcsize_without_its_flag_is_none_of_our_business(monkeypatch):
    """wParam clear means the sender wants only a client rectangle back and none
    of the rest of the calculation. Answering zero to that form too was measured
    to leave the window unable to compute a restore size."""
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome._proc_ref(HWND, chrome_module.WM_NCCALCSIZE, 0, 0) == FORWARDED
    assert api.forwarded[-1][2] == chrome_module.WM_NCCALCSIZE


def test_ncactivate_is_forwarded_with_minus_one(monkeypatch):
    """The default procedure reads lParam as the region to repaint. -1 means
    none of it; without that the frame flickers grey along the top on every
    focus change, repainting a caption that is not there."""
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome._proc_ref(HWND, chrome_module.WM_NCACTIVATE, 1, 0) == FORWARDED
    assert api.forwarded[-1] == (OLD_PROC, HWND, chrome_module.WM_NCACTIVATE, 1, -1)


@pytest.mark.parametrize(
    "message",
    [chrome_module.WM_NCUAHDRAWCAPTION, chrome_module.WM_NCUAHDRAWFRAME],
)
def test_the_undocumented_caption_draws_are_swallowed(message, monkeypatch):
    """Neither message is in any header. The theme manager sends them to draw
    the caption and the frame behind the window procedure's back, and forwarding
    either undoes everything above it."""
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome._proc_ref(HWND, message, 0, 0) == 0
    assert api.forwarded == []


def test_native_loop_requests_cross_onto_the_window_thread(monkeypatch):
    """The bridge runs on a worker thread, but mouse capture belongs to the UI
    thread. The private message crosses that boundary before ReleaseCapture."""
    chrome, api, _ = _chrome(monkeypatch)
    result = chrome._proc_ref(
        HWND,
        chrome_module.WM_APP_START_NATIVE_LOOP,
        chrome_module.HTCAPTION,
        0,
    )
    assert result == 1
    assert api.loops == [(HWND, chrome_module.HTCAPTION)]
    assert api.forwarded == []


def test_every_other_message_passes_straight_through(monkeypatch):
    """Five messages are handled and the rest are the window's own business.
    A procedure that answered more than it had to would be a second, worse
    implementation of Windows."""
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome._proc_ref(HWND, 0x0005, 7, 9) == FORWARDED
    assert api.forwarded[-1] == (OLD_PROC, HWND, 0x0005, 7, 9)


# ---- the title bar's buttons ----


def test_the_eight_edges_are_the_windows_sizing_codes():
    """Spelled the way the C++ sibling spells them, because the same eight names
    are the CSS classes of the grips that send them."""
    assert chrome_module.EDGES == {
        "l": 10,
        "r": 11,
        "t": 12,
        "b": 15,
        "tl": 13,
        "tr": 14,
        "bl": 16,
        "br": 17,
    }


@pytest.mark.parametrize("edge", ["", "x", "L", "middle", None, 3, ["l"]])
def test_an_edge_that_is_not_one_of_the_eight_resolves_to_nothing(edge):
    """None rather than a default corner. A misspelling arriving from the page
    is a bug in the markup, and guessing an edge for it turns "does not resize"
    into "resizes from the wrong corner", which is the harder to notice."""
    assert chrome_module.hit_test(edge) is None


def test_dragging_starts_the_native_move_loop(monkeypatch):
    """`ReleaseCapture` plus a synthetic caption click, which is the line that
    buys Aero Snap, snap-to-edge, drag-to-maximize and shake-to-minimize
    together. Moving the window from mouse positions instead never enters that
    loop, so Windows never offers any of it."""
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome.drag() is True
    assert api.loop_requests == [(HWND, chrome_module.HTCAPTION)]
    assert api.loops == []


@pytest.mark.parametrize("edge,code", sorted(chrome_module.EDGES.items()))
def test_resizing_starts_the_loop_on_the_named_edge(edge, code, monkeypatch):
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome.resize_from(edge) is True
    assert api.loop_requests == [(HWND, code)]
    assert api.loops == []


def test_an_unknown_edge_starts_no_loop_at_all(monkeypatch):
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome.resize_from("nowhere") is False
    assert api.loop_requests == []


def test_minimizing_asks_for_the_taskbar(monkeypatch):
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome.minimize() is True
    assert api.shown == [(HWND, chrome_module.SW_MINIMIZE)]


def test_maximizing_reports_the_state_it_moved_to(monkeypatch):
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome.toggle_maximize() is True
    assert api.shown == [(HWND, chrome_module.SW_MAXIMIZE)]


def test_restoring_reports_the_state_it_moved_to(monkeypatch):
    """False here means "no longer maximized", not "the call failed". The button
    that sent it is the one that has to change glyph."""
    chrome, api, _ = _chrome(monkeypatch, zoomed=True)
    assert chrome.toggle_maximize() is False
    assert api.shown == [(HWND, chrome_module.SW_RESTORE)]


def test_whether_the_window_is_maximized_is_asked_and_not_remembered(monkeypatch):
    """Aero Snap, a double-click on the caption, Win+Up and drag-to-top all
    maximise this window without passing through anything here, so a remembered
    flag is wrong within seconds of the window opening."""
    chrome, api, _ = _chrome(monkeypatch)
    assert chrome.is_maximized() is False
    api.zoomed = True
    assert chrome.is_maximized() is True


def test_closing_goes_through_pywebview(monkeypatch):
    """So pywebview's own shutdown still runs. Destroying the native window
    underneath it leaves the library holding a handle to nothing."""
    chrome, _, window = _chrome(monkeypatch)
    assert chrome.close() is True
    assert window.destroyed == 1


def test_a_window_that_was_never_shown_touches_no_win32(monkeypatch):
    """Everything answers False instead. This is what makes a bridge holding a
    chrome testable with no window in existence, and it is also what happens for
    the few milliseconds between `create_window` and `shown`."""

    def explode():
        raise AssertionError("Win32 was called before the window was shown")

    monkeypatch.setattr(chrome_module, "_win32", explode)
    chrome = WindowChrome(_Window())
    assert chrome.hwnd == 0
    assert chrome.drag() is False
    assert chrome.resize_from("br") is False
    assert chrome.minimize() is False
    assert chrome.toggle_maximize() is False
    assert chrome.is_maximized() is False


# ---- the bridge ----


class _StubChrome:
    """A chrome that records rather than moving anything."""

    def __init__(self, maximized=False):
        self.maximized = maximized
        self.calls = []

    def drag(self):
        self.calls.append("drag")
        return True

    def resize_from(self, edge):
        self.calls.append(("resize", edge))
        return edge in chrome_module.EDGES

    def minimize(self):
        self.calls.append("minimize")
        return True

    def toggle_maximize(self):
        self.calls.append("maximize")
        self.maximized = not self.maximized
        return self.maximized

    def is_maximized(self):
        return self.maximized

    def close(self):
        self.calls.append("close")
        return True


def _calls(bridge):
    return [
        bridge.win_drag(),
        bridge.win_resize("br"),
        bridge.win_min(),
        bridge.win_max(),
        bridge.win_close(),
    ]


def test_the_window_buttons_answer_with_no_chrome_attached():
    """`ok: False` and nothing else. Every test in this suite and every test in
    `tests/test_ui_api.py` builds a bridge with no window behind it, so these
    five have to be answerable rather than skippable."""
    for answer in _calls(Bridge()):
        assert answer["ok"] is False
        assert "error" not in answer


def test_the_window_state_only_advertises_custom_controls_when_supported(monkeypatch):
    bridge = Bridge()
    bridge.attach_chrome(_StubChrome(maximized=True))
    monkeypatch.setattr(chrome_module, "supported", lambda: False)
    assert bridge.win_state() == {"ok": True, "custom": False, "maximized": False}

    monkeypatch.setattr(chrome_module, "supported", lambda: True)
    assert bridge.win_state() == {"ok": True, "custom": True, "maximized": True}


def test_startup_carries_the_window_state_needed_for_the_first_frame(monkeypatch):
    bridge = Bridge()
    bridge.attach_chrome(_StubChrome(maximized=True))
    monkeypatch.setattr(chrome_module, "supported", lambda: True)
    assert bridge.startup()["window"] == {"custom": True, "maximized": True}


def test_the_window_buttons_reach_the_chrome_once_attached():
    bridge = Bridge()
    stub = _StubChrome()
    bridge.attach_chrome(stub)
    assert [a["ok"] for a in _calls(bridge)] == [True, True, True, True, True]
    assert stub.calls == ["drag", ("resize", "br"), "minimize", "maximize", "close"]


def test_maximizing_answers_ok_in_both_directions():
    """A restore is not a failure. Answering with the chrome's own return value
    would make every second click look like one."""
    bridge = Bridge()
    bridge.attach_chrome(_StubChrome())
    assert bridge.win_max() == {"ok": True, "maximized": True}
    assert bridge.win_max() == {"ok": True, "maximized": False}


def test_a_drag_reports_where_it_left_the_window():
    """Dragging to the top of the screen maximises the window, and the button
    that would have said so was never clicked."""
    bridge = Bridge()
    bridge.attach_chrome(_StubChrome(maximized=True))
    assert bridge.win_drag() == {"ok": True, "maximized": True}


def test_an_edge_the_markup_got_wrong_is_answered_and_not_raised():
    bridge = Bridge()
    bridge.attach_chrome(_StubChrome())
    assert bridge.win_resize("nowhere") == {"ok": False}


def test_a_chrome_that_raises_becomes_a_sentence():
    """The same contract as every other method on the bridge: an exception
    reaches Javascript as an opaque Error carrying nothing worth showing to
    somebody who is looking at a window rather than a console."""

    class _Broken(_StubChrome):
        def minimize(self):
            raise RuntimeError("the window went away")

    bridge = Bridge()
    bridge.attach_chrome(_Broken())
    assert bridge.win_min() == {"ok": False, "error": "the window went away"}


def _walkable(obj) -> list:
    """The attributes pywebview would recurse into, by its own rule.

    Mirrors `get_functions` in `webview/util.py`: skip anything whose name
    starts with an underscore, keep methods and functions as leaves, and recurse
    into every class or non-callable object carrying a `__module__`. Written out
    rather than imported because that function is nested inside
    `inject_pywebview` and cannot be reached from here.
    """
    found = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        attr = getattr(obj, name)
        if inspect.ismethod(attr) or inspect.isfunction(attr):
            continue
        if inspect.isclass(attr) or (not callable(attr) and hasattr(attr, "__module__")):
            found.append(name)
    return found


def test_pywebview_can_walk_the_bridge_without_falling_in():
    """The landmine, and it is a hang rather than a crash.

    pywebview builds the Javascript surface by walking this object. A window or
    a chrome on a PUBLIC name sends it into the native form's accessibility
    tree -- `Bounds.Empty.Empty.Empty` -- until the stack ends, and that happens
    inside the injection, so `pywebviewready` never fires and `evaluate_js`
    never returns. The window renders nothing, forever, with no error anywhere.

    Both handles carry a leading underscore for exactly this reason, and this is
    the test that keeps the next one from being added without it.
    """
    bridge = Bridge()
    bridge.attach(_Window())
    bridge.attach_chrome(WindowChrome(_Window()))
    assert _walkable(bridge) == []


def test_the_guard_would_catch_a_handle_left_public():
    """The other half: a check that flags nothing is worth nothing. This is the
    exact mistake, made on purpose."""
    bridge = Bridge()
    bridge.chrome = WindowChrome(_Window())
    assert _walkable(bridge) == ["chrome"]
