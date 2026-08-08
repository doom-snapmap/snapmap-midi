"""The sound palette: which pitches exist, and which sound plays each one.

The palette is a declaration file listing every sound a speaker may play,
grouped into categories. Pitched instrument sounds encode their note in the
name -- `play_violindb6` is D-flat in octave 6 -- so the index is built by
parsing names rather than from any separate table.

That file is extracted game data, so the product does not ship it and does not
know where it is. `snapmap_midi.paths` resolves it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Optional

from snapmap_midi import paths

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
    """Raised when the palette has not been configured (see snapmap_midi.paths)."""


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


def build_note_index(decl_path: Optional[Path] = None) -> dict:
    """Parse the palette into {category: {midi_note: sound}}."""
    path = decl_path or paths.palette_decl()
    if path is None:
        raise PaletteUnavailableError(
            "no sound palette configured; set the palette_decl path (see snapmap_midi.paths)"
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    index: dict = defaultdict(dict)
    for decl, category in _ITEM.findall(text):
        category = category.replace("#str_snap_3dsnd_", "").replace("_title", "")
        m = _NOTE.search(decl)
        if m:
            index[category][note_to_midi(m.group(1), m.group(2), m.group(3))] = decl
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
