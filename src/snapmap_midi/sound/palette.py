"""The sound palette: which sounds exist, and which one plays a given pitch.

The palette is a list of every sound a speaker may play, grouped into
categories. Pitched instrument sounds encode their note in the name --
`play_violindb6` is D-flat in octave 6 -- so the pitch index is built by
parsing names rather than from any separate table.

**The palette ships with this package.** It used to be an extracted game file
the user had to find and configure a path to, which made a fresh install
useless until someone went digging, and made the tool unusable for anyone
without a copy of the extraction. What ships is the list of sound NAMES:
identifiers, not audio, and exactly the kind of data the General MIDI drum
table has always carried inline.

`paths.palette_decl()` remains as an override for the one case that still
needs it -- a game version whose palette differs from the shipped one. Point
it at a speaker declaration and it is parsed in place of the shipped list.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional

from snapmap_midi import paths

#: The shipped palette, alongside the rest of the package's data.
_SHIPPED = Path(__file__).resolve().parents[1] / "data" / "sound_palette.json"

# sound = "<decl>"; text = "..."; desc = "..."; category = "<category>";
_ITEM = re.compile(
    r'sound\s*=\s*"([^"]+)";\s*text\s*=\s*"[^"]*";\s*desc\s*=\s*"[^"]*";\s*category\s*=\s*"([^"]+)";',
    re.S,
)
# A trailing note name: letter, optional flat, octave digit.
_NOTE = re.compile(r"([a-g])(b?)(\d)$")
_PITCH_CLASS = {
    "c": 0,
    "db": 1,
    "d": 2,
    "eb": 3,
    "e": 4,
    "f": 5,
    "gb": 6,
    "g": 7,
    "ab": 8,
    "a": 9,
    "bb": 10,
    "b": 11,
}


class PaletteUnavailableError(RuntimeError):
    """Raised when no palette can be read at all.

    In an intact install this cannot happen -- the palette is package data.
    It means either a broken install or an override path that does not parse.
    """


def note_to_midi(letter: str, accidental: str, octave: str) -> int:
    """Note name components to a MIDI note number."""
    return (int(octave) + 1) * 12 + _PITCH_CLASS[letter + accidental]


def shader_pitch(shader: str) -> Optional[int]:
    """The MIDI pitch encoded in a sound name, or None if it is unpitched.

    Percussion has no pitch in its name, which is exactly how the compiler
    tells a drum hit from a melodic note after the fact.
    """
    m = _NOTE.search(shader)
    return note_to_midi(m.group(1), m.group(2), m.group(3)) if m else None


def _parse_decl(path: Path) -> dict:
    """A speaker declaration to {category: [sound names in order]}."""
    grouped: dict[str, list[str]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for sound, category in _ITEM.findall(text):
        category = category.replace("#str_snap_3dsnd_", "").replace("_title", "")
        grouped.setdefault(category, []).append(sound)
    if not grouped:
        raise PaletteUnavailableError("parsed no sounds from the palette override at %s" % path)
    return grouped


@lru_cache(maxsize=None)
def _load(override: Optional[Path]) -> dict:
    """The palette, read once per distinct source.

    Cached because both the compiler and the audition builder ask for it, and
    a compile with several layers used to re-read and re-parse the whole file
    for each one.
    """
    if override is not None:
        return _parse_decl(override)
    try:
        payload = json.loads(_SHIPPED.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PaletteUnavailableError(
            "the shipped sound palette at %s could not be read (%s); the install is "
            "incomplete" % (_SHIPPED, exc)
        ) from exc
    return payload["categories"]


def load_palette(decl_path: Optional[Path] = None) -> dict:
    """{category: [sound names]}, in declaration order.

    Reads the shipped palette unless an override is given here or configured
    as `palette_decl`.

    Returns a COPY. The parse behind it is cached and shared, so handing the
    cached object out would let one caller's `palette["ins_piano"].pop()`
    silently change what every later compile in the process resolves.
    """
    return {category: list(sounds) for category, sounds in _shared(decl_path).items()}


def _shared(decl_path: Optional[Path] = None) -> dict:
    """The cached parse itself. Internal: callers must not mutate it."""
    return _load(decl_path or paths.palette_decl())


def cache_clear() -> None:
    """Forget the parsed palette.

    Needed because the cache is keyed on the SOURCE, not its contents: after
    regenerating the shipped palette, or pointing `palette_decl` at a rewritten
    file at the same path, the old parse would otherwise be returned for the
    life of the process. The test suite also calls this between tests, since
    the key depends on ambient environment.
    """
    _load.cache_clear()


def categories() -> list:
    """Every category name, in declaration order."""
    return list(_shared())


def sounds_in_category(category: str, decl_path: Optional[Path] = None) -> list:
    """Every sound in a category, in declaration order."""
    return list(_shared(decl_path).get(category, ()))


def build_note_index(decl_path: Optional[Path] = None) -> dict:
    """The pitch index: {category: {midi_note: sound}}.

    Only sounds whose name encodes a note appear. Percussion and effects have
    no pitch, so they are absent by construction rather than by exclusion.
    """
    index: dict = defaultdict(dict)
    for category, sounds in _shared(decl_path).items():
        for sound in sounds:
            m = _NOTE.search(sound)
            if m:
                index[category][note_to_midi(m.group(1), m.group(2), m.group(3))] = sound
    return index


def decl_for(category: str, midi_note: int, index: Mapping) -> Optional[str]:
    """The best sound in `category` for a pitch.

    Exact match wins. Otherwise prefer the same pitch class in another octave
    -- an octave displacement keeps the melody recognisable, where the nearest
    absolute pitch would bend it out of key. Fall back to nearest only when
    the pitch class is absent entirely.
    """
    available = index.get(category)
    if not available:
        return None
    if midi_note in available:
        return available[midi_note]
    pitch_class = midi_note % 12
    same_class = [m for m in available if m % 12 == pitch_class]
    pool = same_class or list(available)
    return available[min(pool, key=lambda m: abs(m - midi_note))]
