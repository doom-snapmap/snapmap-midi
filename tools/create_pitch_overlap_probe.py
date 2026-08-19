"""Test how many generic emitters independently pitched ringing notes need."""

from __future__ import annotations

import argparse
from pathlib import Path

from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map
from snapmap_midi.sound.events import (
    LAYERED_CHANNEL,
    START_CHANNEL,
    events_block,
    fade_pitch,
    start,
    stop,
)
from snapmap_midi.sound.timeline import add_button, ensure_timeline


SAMPLE = "play_pianoc4"


def _timeline_ref(entity: dict) -> str:
    return entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["entity"]


def _pitched_start(time_ms: int, semitones: float) -> list[dict]:
    # Proven clean ordering: pitch precedes start in the equal-time saved array.
    return [
        fade_pitch(time_ms, semitones, 0),
        start(SAMPLE, time_ms, START_CHANNEL),
    ]


def build(path: Path) -> None:
    doc = SnapMapDocument(blank_map(), palette_refs=PRODUCT_PALETTE_REFS)
    master = ensure_timeline(doc)
    master_ref = _timeline_ref(master)
    groups: list[tuple[str, list[dict]]] = [(master_ref, [])]

    # Test A, 0-6 seconds: two long, widely separated pitches reuse ONE
    # concrete-channel emitter. Listen whether the low tail is cut at 1 second.
    one = doc.add_timeline()
    one["displayName"] = "A one emitter: low then high"
    one_events = [
        *_pitched_start(0, -12),
        *_pitched_start(1000, 12),
        stop(6000),
    ]
    groups.append((_timeline_ref(one), one_events))

    # Test B, 8-14 seconds: the same two notes use separate emitters. The low
    # C3 tail should remain clearly audible underneath the C5 note.
    low = doc.add_timeline()
    low["displayName"] = "B1 two emitters: low tail"
    groups.append((_timeline_ref(low), [*_pitched_start(8000, -12), stop(14000)]))

    high = doc.add_timeline()
    high["displayName"] = "B2 two emitters: high answer"
    groups.append((_timeline_ref(high), [*_pitched_start(9000, 12), stop(14000)]))

    # Test C, at 16 seconds: automatic instruments already choose separately
    # tuned shaders. Three simultaneous unbound starts on one generic emitter
    # determine whether that shared emitter can play a native chord without any
    # fadePitch event or dedicated pitch voices.
    automatic = doc.add_timeline()
    automatic["displayName"] = "C native C major chord on one shared emitter"
    automatic_events = [
        start("play_pianoc4", 16000, LAYERED_CHANNEL),
        start("play_pianoe4", 16000, LAYERED_CHANNEL),
        start("play_pianog4", 16000, LAYERED_CHANNEL),
    ]
    groups.append((_timeline_ref(automatic), automatic_events))

    entity_events = {
        f"item[{index}]": {"entity": entity_ref, "events": events_block(events)}
        for index, (entity_ref, events) in enumerate(groups)
    }
    entity_events["num"] = len(groups)
    master["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = entity_events
    add_button(doc, master_ref, "pitch-overlap-probe")

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
        / "pitch_overlap_probe.rawmap.json",
    )
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
