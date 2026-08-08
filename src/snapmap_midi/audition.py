"""Build a map that plays candidate sounds in sequence, so a human can hear them.

The compiler's instrument and drum tables are ultimately ear calls: whether a
given noise reads as a kick or a rim depends on listening to it. This builds a
map whose switch plays each candidate in turn with a printable legend, so
someone can listen through and report back what each index actually sounded
like.

Pure: bytes in, bytes out. Getting the result into a running game is host
tooling, not part of the product.
"""

from __future__ import annotations

from typing import Iterable, Optional

from snapmap_midi.sound import palette, timeline

#: Default spacing. Comfortably clear of the ~1s envelope most samples have,
#: so consecutive candidates do not overlap and blur together.
DEFAULT_GAP_MS = 1500


def candidates_in_category(category: str, decl_path=None) -> list:
    """Every sound in a palette category, in declaration order.

    This used to carry a second copy of the declaration parser, which is how
    it and the pitch index drifted -- two regexes over the same file, one of
    them capturing a field the caller then threw away. It now asks the
    palette, which is the one thing that knows what a palette contains.
    """
    return palette.sounds_in_category(category, decl_path)


def build(
    candidates: Iterable,
    baseline_bytes: Optional[bytes] = None,
    gap_ms: int = DEFAULT_GAP_MS,
    label: str = "snapmap-midi-audition",
) -> bytes:
    """A map whose switch plays each candidate `gap_ms` apart.

    Built through the shared timeline API rather than by hand. This used to be
    a separate copy of the same recipe, which is how the two drifted.
    """
    events = [(sound, i * gap_ms) for i, sound in enumerate(candidates)]
    return timeline.author_sound_timeline(events, baseline_bytes, button_name=label)


def legend(candidates, gap_ms: int = DEFAULT_GAP_MS) -> list[str]:
    """Printable lines pairing each index with when it plays and what it is."""
    return [
        "  {:>2}  t={:>5.1f}s  {}".format(i + 1, i * gap_ms / 1000.0, sound)
        for i, sound in enumerate(candidates)
    ]
