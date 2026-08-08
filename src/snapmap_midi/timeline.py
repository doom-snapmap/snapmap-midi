"""The reusable music-authoring API over a timeline entity.

A note is a scheduled sound-start event. Polyphony is several events at the
same time; layering is several instruments interleaved in one list. A switch
wired to an on-use listener triggers the whole thing.

The map must already contain a timeline entity. That class is special and not
placeable from the palette, so authoring fills an existing one rather than
synthesizing it -- which is why a baseline map is a required input.
"""

from __future__ import annotations

import json
from typing import Iterable, Optional

from snapmap_midi.events import LAYERED_CHANNEL
from snapmap_midi.events import start as _start_event
from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import (
    LISTENER_ON_USE_INHERIT,
    PRODUCT_PALETTE_REFS,
    SWITCH_INHERIT,
)

DEFAULT_CHANNEL = LAYERED_CHANNEL

TIMELINE_CLASS = "idTarget_Timeline"
SWITCH_CLASS = "idInteractable"
LISTENER_CLASS = "idSnapMapListener_Simple"


# ---- event construction ----


def note(shader: str, time_ms: int, channel: str = DEFAULT_CHANNEL):
    """A single scheduled sound."""
    return (shader, int(time_ms), channel)


def chord(shaders: Iterable[str], time_ms: int, channel: str = DEFAULT_CHANNEL):
    """Several sounds at the same instant."""
    return [(s, int(time_ms), channel) for s in shaders]


def melody(shaders: Iterable[str], step_ms: int, start_ms: int = 0, channel: str = DEFAULT_CHANNEL):
    """A sequence of sounds spaced evenly apart."""
    return [(s, start_ms + i * step_ms, channel) for i, s in enumerate(shaders)]


# ---- map mutation ----


def find_timeline(doc: SnapMapDocument) -> dict:
    """The first timeline entity, or raise."""
    for e in doc.data["entities"]:
        if (e.get("entityDef") or {}).get("className") == TIMELINE_CLASS:
            return e
    raise ValueError("no timeline entity in this map; use a baseline that contains one")


def set_events(doc: SnapMapDocument, events) -> str:
    """Schedule (shader, time_ms[, channel]) tuples. Returns the timeline id."""
    events = list(events)
    timeline = find_timeline(doc)
    group = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]["item[0]"]
    items = {}
    for i, event in enumerate(events):
        shader, time_ms = event[0], event[1]
        channel = event[2] if len(event) > 2 else DEFAULT_CHANNEL
        items["item[%d]" % i] = _start_event(shader, time_ms, channel)
    items["num"] = len(events)
    group["events"] = items
    return group["entity"]


def add_button(
    doc: SnapMapDocument,
    timeline_id: str,
    display_name: str = "snapmap-midi-button",
    near_inherit: str = "player_start",
) -> int:
    """Add a switch wired through an on-use listener to `timeline_id`.

    Reference-slot counts come from the document's injected table, not from
    constants written here. Those counts used to be hardcoded at each call
    site precisely because the bulk-extracted table had no entry for the
    switch; naming them in one defensible table is what removed the copies.

    Returns the switch's id. Positions it near the player start so it is
    reachable on spawn.
    """
    entities = doc.data["entities"]
    anchor = next(
        (e for e in entities if near_inherit in ((e.get("entityDef") or {}).get("inherit") or "")),
        None,
    )
    spawn = (anchor["entityDef"]["state"]["edit"].get("spawnPosition", {}) if anchor else {}) or {}
    bx, by, bz = spawn.get("x", 0) + 96, spawn.get("y", 0), spawn.get("z", 0)

    switch_uid = doc.next_safe_uid()
    entities.append(
        doc.build_simple_entity(
            SWITCH_CLASS,
            switch_uid,
            SWITCH_INHERIT,
            {"isReusable": True, "spawnPosition": {"x": bx, "y": by, "z": bz}},
            display_name=display_name,
        )
    )
    doc.extend_instance_entities(switch_uid, 0)
    doc.add_entity_refs(switch_uid, SWITCH_INHERIT)

    listener_uid = doc.next_safe_uid()
    entities.append(
        doc.build_simple_entity(
            LISTENER_CLASS,
            listener_uid,
            LISTENER_ON_USE_INHERIT,
            {
                "spawnPosition": {"x": bx + 16, "y": by + 32, "z": bz + 128},
                "targets": {"item[0]": timeline_id, "num": 1},
            },
        )
    )
    doc.extend_instance_entities(listener_uid, 0)
    doc.add_entity_refs(listener_uid, LISTENER_ON_USE_INHERIT)

    doc.add_connection(switch_uid, listener_uid)
    return switch_uid


def author_sound_timeline(
    baseline, events, button_name: Optional[str] = "snapmap-midi-button"
) -> bytes:
    """Baseline plus events to finished map bytes.

    Pass button_name=None to leave the timeline untriggered, for callers that
    fire it some other way.
    """
    data = baseline if isinstance(baseline, dict) else json.loads(baseline)
    doc = SnapMapDocument(data=data, palette_refs=PRODUCT_PALETTE_REFS)
    timeline_id = set_events(doc, events)
    if button_name:
        add_button(doc, timeline_id, button_name)
    return serialize(doc.data)
