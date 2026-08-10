"""Finding the game install, without asking anybody where it is.

Asking was the old shape of this whole product and it did not work: a first
run that opens on a form demanding a path into a game directory is a first run
most people abandon, and the ones who do not abandon it half get the path
wrong. The install is findable, so it gets found.

The search is ordered and every step is skippable:

    1. the `doom_install` override, for a copy that is somewhere unusual
    2. the Steam library folders, read from Steam's own registry key
    3. the two default Steam directories, for a machine whose registry entry
       has been lost

The first candidate that actually holds soundbanks wins. Existing is not
enough -- a leftover empty folder from a moved or uninstalled copy exists
perfectly well and would send every later read into a directory with nothing
in it.

`None` is an ordinary answer here, not a failure. It means no audio preview,
which is a state the window is built to show; the map still compiles and still
exports, because none of that ever needed the game's samples.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from snapmap_midi import paths
from snapmap_midi.audio import wwise

try:  # pragma: no cover - the import itself is the platform test
    import winreg
except ImportError:
    # Every non-Windows machine. Guarded at import rather than at the call,
    # because an ImportError raised from inside this module would take down
    # anything that merely imported it -- and the honest answer there is
    # "no install found", not a crash.
    winreg = None

#: Where Steam records its own location.
_STEAM_KEY = r"Software\Valve\Steam"
_STEAM_VALUE = "SteamPath"

#: The game, relative to any Steam library root.
INSTALL_SUBDIR = os.path.join("steamapps", "common", "DOOM")

#: Library roots in `libraryfolders.vdf`. Two spellings because Steam changed
#: the file in 2021: newer clients write a `"path"` key inside a numbered
#: block, older ones wrote the path as the numbered key's own value. Matching
#: only the current one silently finds nothing on an older client, which reads
#: exactly like the game not being installed.
_VDF_PATH = re.compile(r'"path"\s*"([^"]*)"')
_VDF_LEGACY = re.compile(r'"\d+"\s*"([a-zA-Z]:[^"]*)"')


def _steam_root() -> Path | None:
    """Steam's own directory, from its registry key, or None."""
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STEAM_KEY) as key:
            value = winreg.QueryValueEx(key, _STEAM_VALUE)[0]
    except OSError:
        # Absent key, absent value, or a permission refusal -- all of them mean
        # the same thing to a caller, and none of them is worth a traceback.
        return None
    return Path(value) if value else None


def _library_roots(steam: Path):
    """Every Steam library root recorded under `steam`, including itself.

    A second library on another drive is the ordinary case for a game this
    size, and it is the case the fallback paths cannot cover: nothing about
    `C:\\Program Files (x86)\\Steam` points at `D:\\SteamLibrary` except this
    file.
    """
    yield steam
    manifest = steam / "steamapps" / "libraryfolders.vdf"
    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for pattern in (_VDF_PATH, _VDF_LEGACY):
        for match in pattern.finditer(text):
            # The file is JSON-ish with escaped separators, and an unescaped
            # read turns `D:\\SteamLibrary` into a name with a doubled
            # separator that resolves nowhere on some inputs.
            yield Path(match.group(1).replace("\\\\", "\\"))


def _default_steam_roots():
    """Where Steam installs itself when nobody moved it.

    Reached only when the registry key is gone -- a repaired profile, a copied
    user directory, or a non-Windows machine running the tests.
    """
    for variable in ("ProgramFiles(x86)", "ProgramW6432", "ProgramFiles"):
        base = os.environ.get(variable)
        if base:
            yield Path(base) / "Steam"


def has_soundbanks(install) -> bool:
    """True when `install` holds a soundbank folder with banks in it.

    The folder's existence alone is not the test. An interrupted install, or a
    copy whose audio has been moved out, leaves the directory behind; treating
    that as found produces a `SoundsUnavailableError` much later, from a
    surface that has already told the user it has audio.
    """
    folder = Path(install) / wwise.SOUND_SUBDIR
    try:
        return any(folder.glob("*.bnk"))
    except OSError:
        return False


def candidates():
    """Every place the game might be, best first.

    Split out from `doom_install` so a caller reporting "not found" can say
    where it looked, which is the difference between a message someone can act
    on and one they can only disbelieve.
    """
    override = paths.doom_install()
    if override is not None:
        yield Path(override)
    steam = _steam_root()
    roots = list(_library_roots(steam)) if steam is not None else []
    for extra in _default_steam_roots():
        if extra not in roots:
            roots.append(extra)
    for root in roots:
        yield root / INSTALL_SUBDIR


def doom_install() -> Path | None:
    """The game install to read audio from, or None if there is not one.

    Returns the first candidate that holds soundbanks. A configured
    `doom_install` therefore wins whenever it is usable -- and when it is not,
    the search carries on rather than stopping, so a stale override does not
    disable audio on a machine that has a perfectly good install elsewhere.
    `paths.resolve` has already warned if the configured path does not exist.
    """
    for candidate in candidates():
        if has_soundbanks(candidate):
            return candidate
    return None
