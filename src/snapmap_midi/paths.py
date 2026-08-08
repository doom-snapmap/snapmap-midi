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
from pathlib import Path

#: Logical names this product understands.
PALETTE_DECL = "palette_decl"
BASELINE_MAP = "baseline_map"
GROOVE_FIXTURE = "groove_fixture"

_ENV = "SNAPMAP_MIDI_PATHS"

#: The one filename the loader reads. Fixed, not a preference.
RAWMAP_NAME = "rawmap.json"

#: The loader's data folder, relative to local application data.
LOADER_DIR_NAME = "snapmap-plus"


def loader_dir() -> Path | None:
    """The folder the map loader reads from, or None off Windows.

    Returns None rather than inventing a path on platforms where the game does
    not run. The caller then writes to the working directory and says so,
    which is more useful than a path nothing will ever read.
    """
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / LOADER_DIR_NAME


def rawmap_destination(out_dir=None) -> Path:
    """Where to write the finished map.

    `out_dir` overrides the folder and nothing else: the filename stays fixed
    because the loader will not read any other one.
    """
    if out_dir is not None:
        return Path(out_dir) / RAWMAP_NAME
    directory = loader_dir()
    return (directory or Path.cwd()) / RAWMAP_NAME


def _config() -> dict:
    raw = (os.environ.get(_ENV) or "").strip()
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
    """Path configured for a logical input, or None if unset or missing."""
    value = _config().get(name)
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def palette_decl() -> Path | None:
    """A speaker declaration to read instead of the shipped sound palette."""
    return resolve(PALETTE_DECL)


def baseline_map() -> Path | None:
    """A saved map to add the song to, instead of authoring a blank one."""
    return resolve(BASELINE_MAP)


def groove_fixture() -> Path | None:
    """The byte-identical regression artifact for the timeline authoring API."""
    return resolve(GROOVE_FIXTURE)


def baseline_configured() -> bool:
    """True when a saved baseline map is available.

    The handful of tests that compile against a real saved map ask this. It
    replaces a `gamedata_configured()` that also demanded the palette -- which
    now ships, so demanding it would skip tests that no longer need anything.
    """
    return baseline_map() is not None
