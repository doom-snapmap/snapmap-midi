"""The reusable music-authoring API over a timeline entity.

A note is a scheduled sound-start event. Polyphony is several events at the
same time; layering is several instruments interleaved in one list. A switch
wired to an on-use listener triggers the whole thing.

Nothing here needs a map to start from. A document that already carries a
timeline keeps the one it has; one that does not gets a freshly authored
timeline entity, and a caller with no document at all gets a blank stage.
"""

from __future__ import annotations

import json
from typing import Iterable, Optional

from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import (
    LISTENER_ON_USE_INHERIT,
    PRODUCT_PALETTE_REFS,
    SWITCH_INHERIT,
)
from snapmap_midi.rawmap.template import blank_map
from snapmap_midi.sound.events import LAYERED_CHANNEL
from snapmap_midi.sound.events import start as _start_event

DEFAULT_CHANNEL = LAYERED_CHANNEL

# The timeline's own class name is NOT restated here. It lives in
# rawmap/template.py, which is what authors the entity; a second copy would be
# a second thing to keep true.
SWITCH_CLASS = "idInteractable"
LISTENER_CLASS = "idSnapMapListener_Simple"


# ---- event construction ----


def chord(shaders: Iterable[str], time_ms: int, channel: str = DEFAULT_CHANNEL):
    """Several sounds at the same instant."""
    return [(s, int(time_ms), channel) for s in shaders]


def melody(shaders: Iterable[str], step_ms: int, start_ms: int = 0, channel: str = DEFAULT_CHANNEL):
    """A sequence of sounds spaced evenly apart."""
    return [(s, start_ms + i * step_ms, channel) for i, s in enumerate(shaders)]


# ---- map mutation ----


def ensure_timeline(doc: SnapMapDocument) -> dict:
    """The document's timeline entity, authoring one if it has none.

    This was `find_timeline`, and it used to raise -- the message told you to
    go and find a baseline map that contained a timeline. That requirement is
    gone: a timeline is describable from nothing, so the honest response to a
    document without one is to write one rather than send the caller away.

    It is not called `find_timeline` any more because it no longer only
    finds. `SnapMapDocument.find_timeline` is the pure query that returns None
    -- two functions a line apart answering to the same name with opposite
    contracts, one of them mutating, is a trap.
    """
    return doc.ensure_timeline()


def set_events(doc: SnapMapDocument, events) -> str:
    """Schedule (shader, time_ms[, channel]) tuples. Returns the timeline id."""
    events = list(events)
    timeline = ensure_timeline(doc)
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
    timeline_id: str | Iterable[str],
    display_name: str = "snapmap-midi-button",
    near_inherit: str = "player_start",
) -> int:
    """Add a switch wired through an on-use listener to one or more timelines.

    Reference-slot counts come from the document's injected table, not from
    constants written here. Those counts used to be hardcoded at each call
    site precisely because the bulk-extracted table had no entry for the
    switch; naming them in one defensible table is what removed the copies.

    Returns the switch's id. Positions it near the player start so it is
    reachable on spawn.
    """
    timeline_ids = [timeline_id] if isinstance(timeline_id, str) else list(timeline_id)
    # A target repeated in the listener would start the same timeline twice.
    # Preserve order while removing duplicates so callers can assemble shard
    # lists without a second bookkeeping structure.
    timeline_ids = list(dict.fromkeys(timeline_ids))
    if not timeline_ids:
        raise ValueError("a button needs at least one timeline target")
    targets = {"item[%d]" % index: target for index, target in enumerate(timeline_ids)}
    targets["num"] = len(timeline_ids)

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
                "targets": targets,
            },
        )
    )
    doc.extend_instance_entities(listener_uid, 0)
    doc.add_entity_refs(listener_uid, LISTENER_ON_USE_INHERIT)

    doc.add_connection(switch_uid, listener_uid)
    return switch_uid


def author_sound_timeline(
    events, baseline=None, button_name: Optional[str] = "snapmap-midi-button"
) -> bytes:
    """Events to finished map bytes.

    `baseline` is optional and exists only for callers who want their sounds
    added to a map they already have. Omit it and the events are staged in a
    blank room authored from nothing, which is the ordinary case.

    Pass button_name=None to leave the timeline untriggered, for callers that
    fire it some other way.
    """
    if baseline is None:
        data = blank_map()
    else:
        data = baseline if isinstance(baseline, dict) else json.loads(baseline)
    doc = SnapMapDocument(data=data, palette_refs=PRODUCT_PALETTE_REFS)
    timeline_id = set_events(doc, events)
    if button_name:
        add_button(doc, timeline_id, button_name)
    return serialize(doc.data)
