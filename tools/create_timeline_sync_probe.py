"""Author an in-game A/B probe for multi-target listener synchronization."""

from __future__ import annotations

import argparse
from pathlib import Path

from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map
from snapmap_midi.sound.events import LAYERED_CHANNEL, events_block, start
from snapmap_midi.sound.timeline import add_button, ensure_timeline

HAT = "play_noise_hat"
CHORD = ("play_pianoc4", "play_pianoe4", "play_pianog4")
PRODUCTION_TARGETS = 33
STRESS_TARGETS = 128


def _timeline_ref(entity: dict) -> str:
    return entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["entity"]


def _set_groups(entity: dict, groups: list[tuple[str, list[dict]]]) -> None:
    entity_events = {
        f"item[{index}]": {"entity": entity_ref, "events": events_block(events)}
        for index, (entity_ref, events) in enumerate(groups)
    }
    entity_events["num"] = len(groups)
    entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = entity_events


def _self_scheduling_timeline(
    doc: SnapMapDocument, display_name: str, events: list[dict]
) -> tuple[dict, str]:
    timeline = doc.add_timeline()
    timeline["displayName"] = display_name
    timeline_ref = _timeline_ref(timeline)
    _set_groups(timeline, [(timeline_ref, events)])
    return timeline, timeline_ref


def build(path: Path) -> None:
    doc = SnapMapDocument(blank_map(), palette_refs=PRODUCT_PALETTE_REFS)

    # A single scheduler is the control. It dispatches the reference chord and
    # reference doubled transient to separate generic emitter entities.
    master = ensure_timeline(doc)
    master["displayName"] = "A/C reference scheduler"
    master_ref = _timeline_ref(master)
    master_groups: list[tuple[str, list[dict]]] = []

    for note_name, shader in zip(("C", "E", "G"), CHORD):
        _, emitter_ref = _self_scheduling_timeline(
            doc, f"A reference chord {note_name} emitter", []
        )
        master_groups.append((emitter_ref, [start(shader, 0, LAYERED_CHANNEL)]))

    # Starting the same sharp transient on two emitters makes even a small
    # onset difference audible as a changed phase/comb sound or a flam.
    for number in (1, 2):
        _, emitter_ref = _self_scheduling_timeline(
            doc, f"C reference doubled hat emitter {number}", []
        )
        master_groups.append((emitter_ref, [start(HAT, 8000, LAYERED_CHANNEL)]))

    _set_groups(master, master_groups)

    # The comparison chord is split across three independently triggered
    # Timeline targets. All three still schedule their own note for 4 seconds.
    trigger_refs = [master_ref]
    for note_name, shader in zip(("C", "E", "G"), CHORD):
        _, timeline_ref = _self_scheduling_timeline(
            doc,
            f"B fanout chord {note_name} shard",
            [start(shader, 4000, LAYERED_CHANNEL)],
        )
        trigger_refs.append(timeline_ref)

    def add_fanout_test(label: str, count: int, time_ms: int) -> None:
        # Only the first and last targets make sound. Empty middle targets force
        # the listener to traverse the entire group without adding unrelated
        # audio, exposing the group's worst first-to-last dispatch skew.
        for index in range(count):
            events = [start(HAT, time_ms, LAYERED_CHANNEL)] if index in (0, count - 1) else []
            _, timeline_ref = _self_scheduling_timeline(
                doc,
                f"{label} fanout target {index + 1:03d}",
                events,
            )
            trigger_refs.append(timeline_ref)

    # Bittersweet Symphony currently compiles to 33 shards. Test that real
    # production-sized fanout before the deliberately excessive stress case.
    add_fanout_test("D production-33", PRODUCTION_TARGETS, 12000)
    add_fanout_test("E stress-128", STRESS_TARGETS, 16000)

    add_button(doc, trigger_refs, "timeline-sync-probe")

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
        / "timeline_sync_probe.rawmap.json",
    )
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
