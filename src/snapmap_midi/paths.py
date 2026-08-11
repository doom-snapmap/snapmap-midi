"""Where the finished map goes, and optional overrides for what goes into it.

## Where the map goes

The map loader reads exactly one file: `rawmap.json`, in its own data folder
under the user's local application data. Not a directory it scans, not a name
it is told -- one hardcoded path. A map written anywhere else, or under any
other name, cannot be loaded without being renamed and moved first.

So that is the default destination, and the filename is not configurable.
Choosing a name that cannot work was the old behaviour and it produced files
that looked finished and were not.

## Optional overrides

Nothing here is required any more, and that is the point. snapmap-midi used to
refuse to run until you found two files inside an installed copy of the game
and configured paths to them: a speaker declaration, and a saved map that
happened to contain a timeline entity. Both are gone. The sound palette ships
with the package, and the map is authored from nothing.

What is left are genuine overrides, for people doing something unusual:

    palette_decl    a speaker declaration to read INSTEAD of the shipped
                    palette, for a game version whose sounds differ
    baseline_map    a saved map to add the song to, instead of staging it in
                    a freshly authored blank room
    groove_fixture  the byte-identical regression artifact for the timeline
                    authoring API; one test, and it is not distributed
    doom_install    the game directory to read audio out of, for a copy the
                    Steam search cannot reach -- a portable install, a second
                    machine's drive, a manually placed copy

Configuration is a JSON object mapping logical name to path, supplied either
inline or as a file:

    SNAPMAP_MIDI_PATHS=/path/to/snapmap-midi-paths.json
    SNAPMAP_MIDI_PATHS={"baseline_map": "..."}

Every resolver returns None when the input has not been configured, which is
the ordinary case rather than an error state.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

#: Logical names this product understands.
PALETTE_DECL = "palette_decl"
BASELINE_MAP = "baseline_map"
GROOVE_FIXTURE = "groove_fixture"
DOOM_INSTALL = "doom_install"

#: The environment variable holding the override table. Public so the test
#: suite can clear it: these overrides are ambient process state, and a suite
#: that reads them is a suite whose result depends on who is running it.
ENV_VAR = "SNAPMAP_MIDI_PATHS"

#: The one filename the loader reads. Fixed, not a preference.
RAWMAP_NAME = "rawmap.json"

#: The loader's data folder, relative to local application data.
LOADER_DIR_NAME = "snapmap-plus"

#: This tool's own data folder, relative to local application data. Distinct
#: from the loader's: that one is somebody else's directory that we write one
#: fixed filename into, this one is ours.
APP_DIR_NAME = "snapmap-midi"

#: Where decoded game audio is cached, under this tool's own folder.
SOUND_CACHE_NAME = "sounds"

#: Numeric analysis only; never decoded audio.
PITCH_PROFILE_NAME = "pitch-profiles-v1.json"


def loader_dir() -> Path | None:
    """The folder the map loader reads from, or None when there isn't one.

    None means `LOCALAPPDATA` is unset, which in practice means a platform the
    game does not run on. Inventing a path there would be worse than admitting
    there is none: the caller writes to the working directory and says so,
    rather than naming a location nothing will ever read.
    """
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / LOADER_DIR_NAME


def sound_cache() -> Path:
    """Where decoded game audio is cached. Always a path, never None.

    Unlike `loader_dir`, this one has no right answer to refuse with. That
    folder is the game loader's and naming a location nothing reads would be a
    lie; this folder is ours, so with no `LOCALAPPDATA` the honest move is to
    pick somewhere in the user's home directory and use it.

    Nothing in here is precious. It is decoded audio from a game the user
    already owns, rebuildable from the install in about 36 seconds, and
    deleting it costs one extraction.
    """
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME / SOUND_CACHE_NAME
    return Path.home() / (".%s" % APP_DIR_NAME) / SOUND_CACHE_NAME


def pitch_profile_cache() -> Path:
    """Where small root-pitch analysis records are persisted."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        base = Path(local) / APP_DIR_NAME
    else:
        base = Path.home() / (".%s" % APP_DIR_NAME)
    return base / PITCH_PROFILE_NAME


def rawmap_destination(out_dir=None) -> Path:
    """Where to write the finished map, as an absolute path.

    `out_dir` overrides the folder and nothing else: the filename stays fixed
    because the loader will not read any other one.

    Resolved rather than returned as given, so that two paths naming the same
    folder compare equal. `--out-dir .` from inside the loader's own folder
    puts the map exactly where it belongs, and an unresolved comparison would
    report that as misplaced.
    """
    directory = Path(out_dir) if out_dir is not None else loader_dir() or Path.cwd()
    return (directory / RAWMAP_NAME).resolve()


def destination_is_loadable(destination: Path) -> bool:
    """True when a map at `destination` is somewhere the loader will read.

    False for every path off the one hardcoded location -- including the
    working-directory fallback, which is a place to put the bytes rather than
    a place the game looks.
    """
    directory = loader_dir()
    if directory is None:
        return False
    return Path(destination).resolve() == (directory / RAWMAP_NAME).resolve()


def _config() -> dict:
    raw = (os.environ.get(ENV_VAR) or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    path = Path(raw)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def resolve(name: str) -> Path | None:
    """Path configured for a logical input, or None if unset or missing.

    A path that is CONFIGURED but does not exist warns before returning None.
    Silence there means a typo degrades into the default and the tool reports
    success while ignoring exactly the thing you asked it to use -- the same
    class of quiet wrong answer as writing a map nothing can load.
    """
    value = _config().get(name)
    if not value:
        return None
    path = Path(value)
    if not path.exists():
        warnings.warn(
            "%s is configured as %r but no such file exists; ignoring it" % (name, str(path)),
            RuntimeWarning,
            stacklevel=2,
        )
        return None
    return path


def palette_decl() -> Path | None:
    """A speaker declaration to read instead of the shipped sound palette."""
    return resolve(PALETTE_DECL)


def baseline_map() -> Path | None:
    """A saved map to add the song to, instead of authoring a blank one."""
    return resolve(BASELINE_MAP)


def groove_fixture() -> Path | None:
    """The byte-identical regression artifact for the timeline authoring API."""
    return resolve(GROOVE_FIXTURE)


def doom_install() -> Path | None:
    """A game directory to read audio from, instead of searching for one."""
    return resolve(DOOM_INSTALL)


def baseline_configured() -> bool:
    """True when a saved baseline map is available.

    The handful of tests that compile against a real saved map ask this. It
    replaces a `gamedata_configured()` that also demanded the palette -- which
    now ships, so demanding it would skip tests that no longer need anything.
    """
    return baseline_map() is not None
