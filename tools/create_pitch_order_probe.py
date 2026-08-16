"""Test whether ``fadePitch`` can be applied without an audible lead-in."""

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
OCTAVE_UP = 12.0
CASE_SPACING_MS = 2000
NOTE_LENGTH_MS = 1000


def _timeline_ref(entity: dict) -> str:
    return entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["entity"]


def _at_case(events: list[dict], index: int) -> list[dict]:
    base = index * CASE_SPACING_MS
    shifted = []
    for event in events:
        event = dict(event)
        event["eventTime"] += base
        shifted.append(event)
    shifted.append(stop(base + NOTE_LENGTH_MS))
    # Python's sort is stable, deliberately preserving the supplied order for
    # equal-time events. Cases 1 and 2 differ only in that order.
    return sorted(shifted, key=lambda event: event["eventTime"])


def build(path: Path) -> None:
    doc = SnapMapDocument(blank_map(), palette_refs=PRODUCT_PALETTE_REFS)
    master = ensure_timeline(doc)
    master_ref = _timeline_ref(master)
    groups: list[tuple[str, list[dict]]] = [(master_ref, [])]

    cases = [
        ("00 baseline C4", [start(SOUND, 0, START_CHANNEL)]),
        (
            "01 equal time: array start then pitch",
            [start(SOUND, 0, START_CHANNEL), fade_pitch(0, OCTAVE_UP, 0)],
        ),
        (
            "02 equal time: array pitch then start",
            [fade_pitch(0, OCTAVE_UP, 0), start(SOUND, 0, START_CHANNEL)],
        ),
    ]
    for delay in (1, 2, 5, 10, 20, 50):
        cases.append(
            (
                f"{len(cases):02d} pitch {delay}ms after start",
                [start(SOUND, 0, START_CHANNEL), fade_pitch(delay, OCTAVE_UP, 0)],
            )
        )

    for index, (name, events) in enumerate(cases):
        emitter = doc.add_timeline()
        emitter["displayName"] = name
        groups.append((_timeline_ref(emitter), _at_case(events, index)))

    entity_events = {
        f"item[{index}]": {"entity": entity_ref, "events": events_block(events)}
        for index, (entity_ref, events) in enumerate(groups)
    }
    entity_events["num"] = len(groups)
    master["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = entity_events
    add_button(doc, master_ref, "pitch-order-probe")

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
        / "pitch_order_probe.rawmap.json",
    )
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
