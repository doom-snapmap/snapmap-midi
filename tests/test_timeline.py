"""The timeline authoring API.

The headline test rebuilds a groove that was verified in game and asserts the
result is byte-identical to the committed artifact, so the API provably still
captures the arrangement that was proven to work.
"""

from __future__ import annotations

import json

import pytest

from snapmap_midi import paths
from snapmap_midi.rawmap.codec import deserialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.timeline import (
    DEFAULT_CHANNEL,
    add_button,
    author_sound_timeline,
    chord,
    find_timeline,
    melody,
    set_events,
)

KICK = "play_noise_kick_tight"
HAT = "play_noise_hat"
CLAP = "play_noise_clap"
BEAT = 400


def _groove_events():
    events = [(HAT, b * BEAT) for b in range(8)]
    events += [(KICK, b * BEAT) for b in (0, 2, 4, 6)]
    events += [(CLAP, b * BEAT) for b in (2, 6)]
    events += [
        ("play_piano" + n, i * BEAT)
        for i, n in enumerate(["e4", "d4", "c4", "d4", "e4", "e4", "e4"])
    ]
    return events


def _doc(minimal_timeline_map) -> SnapMapDocument:
    return SnapMapDocument(data=minimal_timeline_map, palette_refs=PRODUCT_PALETTE_REFS)


# ---- hermetic ----


def test_chord_helper_same_time():
    c = chord(["play_pianoc4", "play_pianoe4", "play_pianog4"], 500)
    assert [t for _, t, _ in c] == [500, 500, 500]
    assert all(ch == DEFAULT_CHANNEL for _, _, ch in c)


def test_melody_helper_spacing():
    m = melody(["a", "b", "c"], step_ms=420, start_ms=100)
    assert [(s, t) for s, t, _ in m] == [("a", 100), ("b", 520), ("c", 940)]


def test_set_events_returns_timeline_id_and_count(minimal_timeline_map):
    doc = _doc(minimal_timeline_map)
    tid = set_events(doc, [("play_pianoc4", 0), ("play_pianod4", 300)])
    assert isinstance(tid, str) and tid
    events = find_timeline(doc)["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["events"]
    assert events["num"] == 2
    assert events["item[0]"]["eventCall"]["args"]["item[0]"] == {"decl": {"sound": "play_pianoc4"}}
    assert events["item[1]"]["eventTime"] == 300


def test_chord_layering_in_one_timeline(minimal_timeline_map):
    doc = _doc(minimal_timeline_map)
    events = chord(["play_pianoc4", "play_pianoe4", "play_pianog4"], 0) + [(KICK, 0)]
    set_events(doc, events)
    items = find_timeline(doc)["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["events"]
    assert items["num"] == 4
    assert all(items["item[%d]" % i]["eventTime"] == 0 for i in range(4))


def test_missing_timeline_is_an_error(minimal_map):
    doc = SnapMapDocument(data=minimal_map, palette_refs=PRODUCT_PALETTE_REFS)
    with pytest.raises(ValueError):
        find_timeline(doc)


def test_add_button_authors_its_reference_slots(minimal_timeline_map):
    """The counts come from the injected table. They were hardcoded at every
    call site before, precisely because the bulk table had no entry for the
    switch -- which is how the copies drifted."""
    doc = _doc(minimal_timeline_map)
    tid = set_events(doc, [("play_pianoc4", 0)])
    before = len(doc.data["references"]["entityEntRefs"]["values"])
    switch_uid = add_button(doc, tid, "test-button")
    after = len(doc.data["references"]["entityEntRefs"]["values"])
    assert after == before + 1  # the switch pair is (1, 0)
    assert doc.get_connections_for_source(switch_uid)


def test_no_button_when_name_is_none(minimal_timeline_map):
    raw = author_sound_timeline(
        json.dumps(minimal_timeline_map).encode(), [("play_pianoc4", 0)], button_name=None
    )
    classes = [(e.get("entityDef") or {}).get("className") for e in deserialize(raw)["entities"]]
    assert "idInteractable" not in classes


def test_roundtrip_preserves_events(minimal_timeline_map):
    raw = author_sound_timeline(
        json.dumps(minimal_timeline_map).encode(),
        [("play_pianoc4", 0), ("play_pianoe4", 250)],
        button_name=None,
    )
    obj = deserialize(raw)
    timeline = next(
        e
        for e in obj["entities"]
        if (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    events = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]["item[0]"][
        "events"
    ]
    assert events["num"] == 2
    assert events["item[1]"]["eventTime"] == 250


# ---- byte gate (needs the real baseline and the committed artifact) ----


@pytest.mark.gamedata
def test_reproduces_proven_groove_byte_identical():
    # This one needs a third input beyond the two the gamedata marker checks.
    # Skip on it explicitly rather than dereferencing None: a partial
    # configuration should degrade, not crash.
    fixture = paths.groove_fixture()
    if fixture is None:
        pytest.skip("no groove_fixture configured (see snapmap_midi.paths)")
    raw = author_sound_timeline(
        paths.baseline_map().read_bytes(), _groove_events(), button_name="claude-groove-button"
    )
    assert raw == fixture.read_bytes(), "API output diverged from the artifact proven in game"
