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

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from snapmap_midi import paths, timeline
from snapmap_midi.palette import PaletteUnavailableError
from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS

#: Default spacing. Comfortably clear of the ~1s envelope most samples have,
#: so consecutive candidates do not overlap and blur together.
DEFAULT_GAP_MS = 1500

_ITEM = re.compile(
    r'sound\s*=\s*"([^"]+)";\s*text\s*=\s*"([^"]+)";\s*desc\s*=\s*"[^"]*";\s*category\s*=\s*"([^"]+)";',
    re.S,
)


def candidates_in_category(category: str, decl_path: Optional[Path] = None):
    """[(sound, label)] for a palette category, in declaration order."""
    path = decl_path or paths.palette_decl()
    if path is None:
        raise PaletteUnavailableError(
            "no sound palette configured; set the palette_decl path (see snapmap_midi.paths)"
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    grouped = defaultdict(list)
    for sound, label, cat in _ITEM.findall(text):
        cat = cat.replace("#str_snap_3dsnd_", "").replace("_title", "")
        grouped[cat].append((sound, label))
    return grouped.get(category, [])


def build(
    candidates: Iterable,
    baseline_bytes: bytes,
    gap_ms: int = DEFAULT_GAP_MS,
    label: str = "snapmap-midi-audition",
) -> bytes:
    """A map whose switch plays each candidate `gap_ms` apart.

    Built through the shared timeline API rather than by hand. This used to be
    a separate copy of the same recipe, which is how the two drifted.
    """
    doc = SnapMapDocument(data=json.loads(baseline_bytes), palette_refs=PRODUCT_PALETTE_REFS)
    events = [(sound, i * gap_ms) for i, (sound, _label) in enumerate(candidates)]
    timeline_id = timeline.set_events(doc, events)
    timeline.add_button(doc, timeline_id, label)
    return serialize(doc.data)


def legend(candidates, gap_ms: int = DEFAULT_GAP_MS) -> list[str]:
    """Printable lines pairing each index with when it plays and what it is."""
    return [
        "  {:>2}  t={:>5.1f}s  {}".format(i + 1, i * gap_ms / 1000.0, sound)
        for i, (sound, _label) in enumerate(candidates)
    ]
