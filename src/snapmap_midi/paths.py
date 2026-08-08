"""Resolve the game-derived inputs snapmap-midi needs, without knowing where they live.

snapmap-midi compiles music for a game whose data it may not redistribute: the
speaker palette declaration and the baseline map are extracted game assets. The
product therefore never hardcodes a location for them. It names them logically
and asks the host to say where they are.

Configuration is a JSON object mapping logical name to path, supplied either
inline or as a file:

    SNAPMAP_MIDI_PATHS=/path/to/snapmap-midi-paths.json
    SNAPMAP_MIDI_PATHS={"palette_decl": "...", "baseline_map": "..."}

Every resolver returns None when the input has not been configured, so callers
can degrade or skip rather than crash. This module is also the reason the
product stays relocatable: nothing here resolves against a specific repository
layout, so moving snapmap-midi to its own repository changes no code.
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
    """The speaker palette declaration the note index is built from."""
    return resolve(PALETTE_DECL)


def baseline_map() -> Path | None:
    """A saved map containing a timeline entity, used as the compile baseline."""
    return resolve(BASELINE_MAP)


def groove_fixture() -> Path | None:
    """The byte-identical regression artifact for the timeline authoring API."""
    return resolve(GROOVE_FIXTURE)


def gamedata_configured() -> bool:
    """True when the palette and baseline are both resolvable."""
    return palette_decl() is not None and baseline_map() is not None
