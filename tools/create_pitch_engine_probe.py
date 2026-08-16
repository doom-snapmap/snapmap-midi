"""Author an in-game matrix that isolates DOOM's ``fadePitch`` behavior."""

from __future__ import annotations

import argparse
from pathlib import Path

from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SPEAKER_INHERIT, SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map, speaker_position
from snapmap_midi.sound.events import (
    LAYERED_CHANNEL,
    START_CHANNEL,
    events_block,
    fade_pitch,
    start,
    stop,
)
from snapmap_midi.sound.timeline import add_button, ensure_timeline


SOUND = "play_pianoc4"
OCTAVE_UP = 12.0
CASE_SPACING_MS = 2000
NOTE_LENGTH_MS = 1000


def _timeline_ref(entity: dict) -> str:
    return entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["entity"]


def _case(events, index: int) -> list[dict]:
    """Move a zero-based case to its audible slot and stop its bound sound."""

    base = index * CASE_SPACING_MS
    shifted = []
    for event in events:
        event = dict(event)
        event["eventTime"] += base
        shifted.append(event)
    shifted.append(stop(base + NOTE_LENGTH_MS))
    return sorted(shifted, key=lambda event: event["eventTime"])


def build(path: Path) -> None:
    doc = SnapMapDocument(blank_map(), palette_refs=PRODUCT_PALETTE_REFS)
    master = ensure_timeline(doc)
    master_ref = _timeline_ref(master)
    groups: list[tuple[str, list[dict]]] = [(master_ref, [])]

    generic_cases = [
        (
            "00 baseline: generic MUSIC1, no pitch",
            [start(SOUND, 0, START_CHANNEL)],
        ),
        (
            "01 generic MUSIC1 start, ANY pitch, same time",
            [start(SOUND, 0, START_CHANNEL), fade_pitch(0, OCTAVE_UP, 0, LAYERED_CHANNEL)],
        ),
        (
            "02 generic MUSIC1 start, ANY pitch after 50ms",
            [start(SOUND, 0, START_CHANNEL), fade_pitch(50, OCTAVE_UP, 0, LAYERED_CHANNEL)],
        ),
        (
            "03 generic MUSIC1 start and pitch, same time",
            [start(SOUND, 0, START_CHANNEL), fade_pitch(0, OCTAVE_UP, 0, START_CHANNEL)],
        ),
        (
            "04 generic MUSIC1 start, MUSIC1 pitch after 50ms over 0.25s",
            [start(SOUND, 0, START_CHANNEL), fade_pitch(50, OCTAVE_UP, 0.25, START_CHANNEL)],
        ),
        (
            "05 generic ANY pitch 50ms before MUSIC1 start",
            [fade_pitch(0, OCTAVE_UP, 0, LAYERED_CHANNEL), start(SOUND, 50, START_CHANNEL)],
        ),
    ]

    for index, (name, events) in enumerate(generic_cases):
        emitter = doc.add_timeline()
        emitter["displayName"] = name
        groups.append((_timeline_ref(emitter), _case(events, index)))

    module = doc.module_stem()
    speaker_uid = doc.add_speaker(
        sound=SOUND,
        position=speaker_position(0),
        display_name="06-07 speaker fadePitch controls",
    )
    speaker_ref = f"0_{module}/{SPEAKER_INHERIT}_{speaker_uid}"
    speaker_events = []
    speaker_events.extend(
        _case(
            [start(SOUND, 0, START_CHANNEL), fade_pitch(0, OCTAVE_UP, 0, LAYERED_CHANNEL)],
            6,
        )
    )
    speaker_events.extend(
        _case(
            [start(SOUND, 0, START_CHANNEL), fade_pitch(50, OCTAVE_UP, 0.25, START_CHANNEL)],
            7,
        )
    )
    groups.append((speaker_ref, sorted(speaker_events, key=lambda event: event["eventTime"])))

    # Keep the unbound-start experiment last: by design an ANY start cannot be
    # stopped through a channel, so its tail must not overlap later cases.
    any_emitter = doc.add_timeline()
    any_emitter["displayName"] = "08 generic ANY start and ANY pitch, same time"
    any_events = [
        start(SOUND, 8 * CASE_SPACING_MS, LAYERED_CHANNEL),
        fade_pitch(8 * CASE_SPACING_MS, OCTAVE_UP, 0, LAYERED_CHANNEL),
    ]
    groups.append((_timeline_ref(any_emitter), any_events))

    entity_events = {
        f"item[{index}]": {"entity": entity_ref, "events": events_block(events)}
        for index, (entity_ref, events) in enumerate(groups)
    }
    entity_events["num"] = len(groups)
    master["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = entity_events
    add_button(doc, master_ref, "pitch-engine-probe")

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
        / "pitch_engine_probe.rawmap.json",
    )
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
