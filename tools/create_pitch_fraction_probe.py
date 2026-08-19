"""Test fractional ``fadePitch`` values on the proven zero-delay route."""

from __future__ import annotations

import argparse
from pathlib import Path

from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map
from snapmap_midi.sound.events import START_CHANNEL, events_block, fade_pitch, start, stop
from snapmap_midi.sound.timeline import add_button, ensure_timeline


SOUND = "play_pianoc4"
CASE_SPACING_MS = 2000
NOTE_LENGTH_MS = 1000
PITCHES = (0.0, 0.25, 0.5, 0.75, 1.0, -0.25, -0.5, -0.75, -1.0, 12.0)


def _timeline_ref(entity: dict) -> str:
    return entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["entity"]


def build(path: Path) -> None:
    doc = SnapMapDocument(blank_map(), palette_refs=PRODUCT_PALETTE_REFS)
    master = ensure_timeline(doc)
    master_ref = _timeline_ref(master)
    groups: list[tuple[str, list[dict]]] = [(master_ref, [])]

    for index, pitch in enumerate(PITCHES):
        emitter = doc.add_timeline()
        emitter["displayName"] = f"{index:02d} pitch {pitch:+g} semitones"
        base = index * CASE_SPACING_MS
        if pitch:
            # Proven engine order: pitch must precede start in the serialized
            # equal-time array. DOOM then applies it at onset without a glide.
            events = [
                fade_pitch(base, pitch, 0),
                start(SOUND, base, START_CHANNEL),
                stop(base + NOTE_LENGTH_MS),
            ]
        else:
            events = [start(SOUND, base, START_CHANNEL), stop(base + NOTE_LENGTH_MS)]
        groups.append((_timeline_ref(emitter), events))

    entity_events = {
        f"item[{index}]": {"entity": entity_ref, "events": events_block(events)}
        for index, (entity_ref, events) in enumerate(groups)
    }
    entity_events["num"] = len(groups)
    master["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = entity_events
    add_button(doc, master_ref, "pitch-fraction-probe")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize(doc.data))
    print(path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "examples"
        / "pitch_fraction_probe.rawmap.json",
    )
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
