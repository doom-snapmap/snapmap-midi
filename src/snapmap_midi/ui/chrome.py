"""One header instead of two: taking the native title bar off a real window.

The window draws its own menubar in HTML. Until this module existed the
operating system drew a title bar above that menubar, so every session opened
with two stacked headers and the top one was empty. The C++ sibling never had
that problem -- its window procedure consumes `WM_NCCALCSIZE`, so the web view
fills the entire window and the caption is never drawn at all. This is the same
trick reached through ctypes, because the window here belongs to pywebview
rather than to us.

It is deliberately NOT pywebview's `frameless=True`. Measured on pywebview
6.2.1, that option leaves window style 0x16010000: WS_VISIBLE, WS_CLIPSIBLINGS,
WS_CLIPCHILDREN, WS_MAXIMIZEBOX and nothing else. No WS_THICKFRAME means no
resize borders and no Aero Snap; no WS_MINIMIZEBOX means the taskbar button
will not minimise it; no WS_SYSMENU means Alt+Space is dead and maximising
covers the taskbar. Keeping an ordinary window and eating its non-client area
instead leaves style 0x16CF0000 -- every one of those bits intact -- because it
stays the window Windows already knew how to manage.

Six things below look like detail and are each a measured failure:

Installation has two stages because pywebview fires them on different threads.
The WinForms border bookkeeping is changed on `before_show`, synchronously on
the UI thread. Doing that from the background `shown` callback deadlocks with
WebView2 focus and leaves a blank, non-responsive window. The Win32 procedure is
still installed on `shown`: subclassing it before the form has settled was also
measured to hang the web view's handshake.

The window procedure object is stored on the instance. It is a ctypes
trampoline, and nothing but that attribute refers to it once `_install`
returns. Collected, Windows calls freed memory on the next message and the
process dies with no traceback and no exit message.

`WM_NCCALCSIZE` insets the client rectangle when the window is maximised.
Maximised, Windows pushes the window a resize frame past the work area on every
side; a client that spans the whole window then hangs off the monitor and
covers the taskbar. Insetting by SM_CXFRAME + SM_CXPADDEDBORDER puts it back
exactly on the work area.

`WM_NCACTIVATE` forwards with lParam -1. Without it the default procedure
repaints a caption that is not there and the top of the window flickers grey on
every focus change.

WM_NCUAHDRAWCAPTION and WM_NCUAHDRAWFRAME -- undocumented, sent by the theme
manager -- are swallowed, for the same reason.

The frame is extended one pixel into the client area. That single pixel is what
makes the compositor draw the drop shadow and the Windows 11 rounded corners on
a window with no caption; at zero there is neither, and the window reads as a
flat rectangle pasted on the desktop.

Dragging and resizing are `ReleaseCapture` plus a synthetic WM_NCLBUTTONDOWN,
which hands the mouse to Windows' own modal move loop. That one line is what
buys Aero Snap, snap-to-edge, drag-to-maximize, shake-to-minimize and
multi-monitor DPI correctness together. Moving the window from mousemove events
instead never enters that loop, so Windows never offers any of it -- and costs
a round trip per mouse position on top.
"""

from __future__ import annotations

import ctypes

#: Window-long indices: the style word, and the window procedure pointer.
GWL_STYLE = -16
GWLP_WNDPROC = -4

#: The styles a window needs to be managed like every other window. These are
#: re-added rather than assumed: what is being removed here is the DRAWING of
#: the frame, never the behaviour behind it. WS_CAPTION is in the list even
#: though there is no caption -- the compositor reads it to decide that this
#: window gets a shadow and the open, minimise and restore animations, and a
#: window without it snaps in and out of existence.
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
MANAGED_STYLES = WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU

WM_NCCALCSIZE = 0x0083
WM_NCACTIVATE = 0x0086
WM_NCLBUTTONDOWN = 0x00A1
#: Private message used to cross from pywebview's bridge worker to the
#: WinForms UI thread before beginning a native move or resize loop.
WM_APP_START_NATIVE_LOOP = 0x8001

#: Undocumented, and absent from every header. The theme manager sends these to
#: draw the caption and frame behind the window procedure's back.
WM_NCUAHDRAWCAPTION = 0x00AE
WM_NCUAHDRAWFRAME = 0x00AF

#: Hit-test codes. Passed as the wParam of a synthetic WM_NCLBUTTONDOWN, each
#: one names which modal loop Windows should start.
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

SM_CXFRAME = 32
SM_CYFRAME = 33
SM_CXPADDEDBORDER = 92

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9

#: One pixel of frame extended into the client area, which is the whole of what
#: makes the compositor draw a shadow and rounded corners on a captionless
#: window. Zero gets neither.
SHADOW_MARGIN = 1

#: The eight edge names Javascript may ask to resize by, spelled exactly as the
#: C++ sibling spells them, mapped to the sizing loop each one starts. The names
#: are short because they are also the CSS class of the grip that sends them.
EDGES = {
    "l": HTLEFT,
    "r": HTRIGHT,
    "t": HTTOP,
    "b": HTBOTTOM,
    "tl": HTTOPLEFT,
    "tr": HTTOPRIGHT,
    "bl": HTBOTTOMLEFT,
    "br": HTBOTTOMRIGHT,
}


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    """What WM_NCCALCSIZE points at. Only `rgrc[0]` -- the proposed client
    rectangle -- is written here; the other two are the old client rectangle and
    the old window rectangle, and rewriting either asks the compositor to
    animate a move that is not happening."""

    _fields_ = [("rgrc", RECT * 3), ("lppos", ctypes.c_void_p)]


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def supported() -> bool:
    """True when this process can call Win32 at all.

    False everywhere but Windows, and there it is checked before anything is
    installed rather than caught afterwards: a window that cannot be reframed
    is a window with a title bar, which is worse than the old behaviour but not
    a reason to fail to open.
    """
    return hasattr(ctypes, "windll")


def hit_test(edge) -> int | None:
    """The sizing loop an edge name starts, or None for a name that is not one.

    None rather than a default edge. A misspelling arriving from Javascript is
    a bug in the markup, and guessing `HTBOTTOMRIGHT` for it would make that bug
    a window that resizes from the wrong corner instead of one that does not
    resize -- which is the harder of the two to notice.
    """
    return EDGES.get(edge) if isinstance(edge, str) else None


def tell_the_form_its_frame_is_gone(native) -> bool:
    """Stop the window growing by a title bar every time it is restored.

    The one thing here that is not Win32. pywebview's window is a WinForms
    form, and .NET keeps its own idea of the border style: leaving the normal
    state it stores the CLIENT size, and coming back it turns that into a
    window size with AdjustWindowRectEx for the border style it believes the
    form has. Consuming the non-client area makes the client the whole window,
    so that round trip hands back a window one frame and one caption larger
    than it went in -- measured at 16 x 39 pixels per cycle, on maximise AND on
    minimise, and it compounds until the window is off the screen.

    Setting the form's border style to none corrects that arithmetic and
    touches nothing else: it is .NET's bookkeeping, not the window, and the
    live style is set to what this module wants immediately afterwards. This
    must run from pywebview's synchronous `before_show` event; assigning a
    WinForms property from the background `shown` event deadlocks WebView2.
    False when there is no .NET to tell -- the window still works, it just
    creeps.
    """
    try:
        from System.Windows.Forms import FormBorderStyle

        # `None` is a keyword here and a member name there.
        native.FormBorderStyle = getattr(FormBorderStyle, "None")
    except Exception:
        return False
    return True


def nccalcsize_params(lparam: int) -> NCCALCSIZE_PARAMS:
    """The structure WM_NCCALCSIZE's lParam points at, as a live view of it.

    A view and not a copy: the rectangle is an out-parameter, so the caller's
    edits have to land in the sender's own memory.
    """
    return ctypes.cast(lparam, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents


class _Win32:
    """The dozen entry points this needs, bound once and named for intent.

    Bound on first use rather than at import. `ctypes.windll`,
    `ctypes.WINFUNCTYPE` and `ctypes.wintypes` all exist on Windows alone, and
    the test suite imports this module on whatever machine is running it -- the
    same reason `ui/app.py` keeps `import webview` inside `run`.

    Argument types are declared on every call that takes a pointer-sized value.
    ctypes defaults an undeclared argument to C `int`, and a window handle or a
    procedure address truncated to 32 bits is a wrong pointer that Windows will
    dereference without complaint.

    `wintypes` is not used even here: HWND is `c_void_p`, WPARAM is `c_size_t`
    and LPARAM is `c_ssize_t` under those names, so spelling them this way costs
    nothing and keeps the import off the module's top level.
    """

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._dwmapi = ctypes.windll.dwmapi

        self.WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )

        self._get_long = self._user32.GetWindowLongPtrW
        self._get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._get_long.restype = ctypes.c_void_p

        self._set_long = self._user32.SetWindowLongPtrW
        self._set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self._set_long.restype = ctypes.c_void_p

        self._call_proc = self._user32.CallWindowProcW
        self._call_proc.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self._call_proc.restype = ctypes.c_ssize_t

        self._send_message = self._user32.SendMessageW
        self._send_message.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self._send_message.restype = ctypes.c_ssize_t

    def wrap_proc(self, function):
        """A Win32 callable for a Python function.

        The result must outlive the window. It is the machine code Windows will
        jump to, and nothing on the Win32 side keeps it alive.
        """
        return self.WNDPROC(function)

    def window_proc(self, hwnd: int) -> int:
        return self._get_long(hwnd, GWLP_WNDPROC)

    def set_window_proc(self, hwnd: int, proc) -> None:
        self._set_long(hwnd, GWLP_WNDPROC, ctypes.cast(proc, ctypes.c_void_p).value)

    def call_window_proc(self, proc: int, hwnd, message: int, wparam: int, lparam: int) -> int:
        return self._call_proc(ctypes.c_void_p(proc), hwnd, message, wparam, lparam)

    def window_style(self, hwnd: int) -> int:
        return self._get_long(hwnd, GWL_STYLE)

    def set_window_style(self, hwnd: int, style: int) -> None:
        self._set_long(hwnd, GWL_STYLE, ctypes.c_void_p(style))

    def system_metric(self, index: int) -> int:
        return int(self._user32.GetSystemMetrics(index))

    def is_zoomed(self, hwnd) -> bool:
        return bool(self._user32.IsZoomed(ctypes.c_void_p(hwnd)))

    def show_window(self, hwnd: int, command: int) -> None:
        self._user32.ShowWindow(ctypes.c_void_p(hwnd), command)

    def refresh_frame(self, hwnd: int) -> None:
        """Ask for a frame recalculation now.

        Without it the caption lingers until the first move or resize, so the
        window opens with the very header this module exists to remove and then
        loses it under the user's hand.
        """
        self._user32.SetWindowPos(
            ctypes.c_void_p(hwnd),
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

    def extend_frame(self, hwnd: int, margin: int) -> None:
        margins = MARGINS(margin, margin, margin, margin)
        self._dwmapi.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd), ctypes.byref(margins))

    def start_native_loop(self, hwnd: int, code: int) -> None:
        """Hand the mouse to Windows' own move or size loop.

        This must run on the window's UI thread. Mouse capture belongs to the
        thread that owns the WebView control, so releasing it from pywebview's
        bridge worker does nothing and the window stays nailed in place.
        """
        self._user32.ReleaseCapture()
        self._send_message(ctypes.c_void_p(hwnd), WM_NCLBUTTONDOWN, code, 0)

    def request_native_loop(self, hwnd: int, code: int) -> bool:
        """Synchronously ask the UI-thread window procedure to start the loop.

        `SendMessageW` crosses to the owning thread and waits. The private
        message is handled by our installed procedure, which releases capture
        there and enters Windows' modal move/size loop. It returns only after
        the mouse is released, so the bridge answer describes the final state.
        """
        return bool(
            self._send_message(
                ctypes.c_void_p(hwnd),
                WM_APP_START_NATIVE_LOOP,
                code,
                0,
            )
        )


_api = None


def _win32() -> _Win32:
    """The Win32 facade, built once. Replaced wholesale by the test suite, which
    is how every branch below is exercised without a window existing."""
    global _api
    if _api is None:
        _api = _Win32()
    return _api


class WindowChrome:
    """Takes the frame off one pywebview window and answers its title bar.

    Constructed with the window and installed later. WinForms bookkeeping is
    corrected on `before_show`, while pywebview is still on its UI thread; the
    native frame is removed on `shown`, once the form has settled.

    Every method answers False rather than raising when the window has not been
    shown yet, so a bridge holding one of these is testable with no window in
    existence -- which is the only way any of this gets tested at all.
    """

    def __init__(self, window):
        # Private for the same reason the bridge's own handles are: pywebview
        # walks every PUBLIC non-callable attribute of the object it is given as
        # a Javascript surface, and a window reached that way recurses through
        # the form's accessibility tree until the stack ends. Nothing exposes
        # this object to that walk today, and the underscore is what keeps that
        # true if something ever does.
        self._window = window
        self._old_proc = None
        # Load-bearing. This is the only reference to the ctypes trampoline
        # Windows jumps to; collected, the next message reaches freed memory and
        # the process disappears without a traceback.
        self._proc_ref = None
        #: The handle, once there is one. Zero until then, and every method
        #: reads it as "nothing has been installed".
        self.hwnd = 0
        window.events.before_show += self._prepare_form
        window.events.shown += self._install

    # ---- installation ----

    def _prepare_form(self, window=None) -> None:
        """Correct WinForms' size bookkeeping on its own UI thread.

        `before_show` is a locking pywebview event and therefore runs inline on
        the WinForms thread. The later `shown` event runs handlers on a Python
        worker; writing `FormBorderStyle` there blocks that worker while the UI
        thread blocks in WebView2 focus, so neither can finish and the page is
        never painted.
        """
        if not supported():
            return
        native = getattr(self._window, "native", None)
        if native is None:
            return
        tell_the_form_its_frame_is_gone(native)

    def _install(self, window=None) -> None:
        """Strip the frame, the first moment there is a frame to strip.

        Registered on `shown`, which pywebview runs on a worker thread and whose
        exceptions it swallows into a log record. A failure in here is therefore
        a window that still has its caption and no other symptom, which is why
        the two conditions that can genuinely be absent -- Win32, and the native
        form -- are checked rather than left to raise.
        """
        if not supported():
            return
        native = getattr(self._window, "native", None)
        if native is None:
            return

        self.hwnd = int(native.Handle.ToInt64())
        api = _win32()

        # There is no SM_CYPADDEDBORDER: the padded border is one number and
        # applies to both axes.
        frame_x = api.system_metric(SM_CXFRAME) + api.system_metric(SM_CXPADDEDBORDER)
        frame_y = api.system_metric(SM_CYFRAME) + api.system_metric(SM_CXPADDEDBORDER)

        old = api.window_proc(self.hwnd)

        def proc(handle, message, wparam, lparam):
            if message == WM_APP_START_NATIVE_LOOP:
                api.start_native_loop(handle, int(wparam))
                return 1
            if message == WM_NCCALCSIZE and wparam:
                if api.is_zoomed(handle):
                    params = nccalcsize_params(lparam)
                    params.rgrc[0].left += frame_x
                    params.rgrc[0].right -= frame_x
                    params.rgrc[0].top += frame_y
                    params.rgrc[0].bottom -= frame_y
                return 0
            if message == WM_NCACTIVATE:
                return api.call_window_proc(old, handle, message, wparam, -1)
            if message in (WM_NCUAHDRAWCAPTION, WM_NCUAHDRAWFRAME):
                return 0
            return api.call_window_proc(old, handle, message, wparam, lparam)

        self._old_proc = old
        self._proc_ref = api.wrap_proc(proc)
        api.set_window_proc(self.hwnd, self._proc_ref)

        # `before_show` already corrected the form's bookkeeping. Re-add the
        # live native styles afterwards because setting FormBorderStyle makes
        # .NET push its own idea of those bits at the HWND.
        api.set_window_style(self.hwnd, api.window_style(self.hwnd) | MANAGED_STYLES)
        api.extend_frame(self.hwnd, SHADOW_MARGIN)
        api.refresh_frame(self.hwnd)

    # ---- what the title bar does ----

    def drag(self) -> bool:
        """Move the window with the mouse, the way Windows moves windows."""
        if not self.hwnd:
            return False
        return _win32().request_native_loop(self.hwnd, HTCAPTION)

    def resize_from(self, edge) -> bool:
        """Size the window from one of the eight edges, or answer False."""
        code = hit_test(edge)
        if code is None or not self.hwnd:
            return False
        return _win32().request_native_loop(self.hwnd, code)

    def minimize(self) -> bool:
        if not self.hwnd:
            return False
        _win32().show_window(self.hwnd, SW_MINIMIZE)
        return True

    def toggle_maximize(self) -> bool:
        """Maximise or restore, and answer with the state it moved TO.

        The state it moved to rather than a bare success, because the button
        that sent this is the one that has to change glyph and nothing else on
        the page knows which way it went.
        """
        if not self.hwnd:
            return False
        zoomed = self.is_maximized()
        _win32().show_window(self.hwnd, SW_RESTORE if zoomed else SW_MAXIMIZE)
        return not zoomed

    def is_maximized(self) -> bool:
        """Asked of Windows every time rather than remembered.

        Aero Snap, a double-click on the caption, Win+Up and drag-to-top all
        maximise this window without going through anything here, so a
        remembered flag is wrong within about four seconds of the window
        opening.
        """
        if not self.hwnd:
            return False
        return _win32().is_zoomed(self.hwnd)

    def close(self) -> bool:
        """Close through pywebview, so its own shutdown still runs."""
        self._window.destroy()
        return True
