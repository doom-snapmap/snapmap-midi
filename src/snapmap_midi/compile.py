"""Orchestration: a MIDI file becomes a playable map.

Scheduling follows expression and decay independently:

  - Neutral decaying notes layer polyphonically on the shared Timeline entity.
  - Decaying notes with pitch or gain use isolated, duration-reserved Timeline emitters
    and are left to fade on their own.
  - Sustained notes use isolated Timeline emitters plus explicit stops or releases.

Voice preparation is shared with browser preview. Per-track voice caps keep an
instrument from monopolising the song, then a global pool enforces the map's
total emitter budget. Density controls reduce exposure to the engine's
emitter-recycling limit; per-note pitch and volume controls describe expression
and do not change that limit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from snapmap_midi.music.midi import for_part, parse_notes
from snapmap_midi.music.voices import (
    allocate_voices,
    apply_glides,
    apply_voice_cap,
    prepare_voice_layers,
    thin_global_polyphony,
    thin_polyphony,
    thin_simultaneous,
)
from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map, timeline_position_after_interactive
from snapmap_midi.sound import events as _events
from snapmap_midi.sound.timeline import add_button, ensure_timeline

#: The largest timeline the SnapMap editor can OPEN, in serialized bytes.
#:
#: The engine serializes one entity into a fixed buffer and reports only a byte
#: count, so a timeline past that buffer comes back as a plain failure: the
#: editor says it cannot open the timeline and nothing says why. The map still
#: LOADS and the music still PLAYS -- only editing is lost -- which is what made
#: this so hard to place.
#:
#: Bisected in game over eight loads, measuring the timeline entity through this
#: module's own serializer, so the numbers below compare directly with
#: `stats["timeline_bytes"]`:
#:
#:     1,081,338 bytes  opens
#:     1,091,628 bytes  refuses
#:
#: That is 1.036x one MiB, consistent with a 1 MiB buffer on the engine's side
#: and our compact JSON running a few percent fatter than what it writes. The
#: budget is set at one MiB rather than at the measured line: it is below every
#: size proven to open, it is the round number the evidence points at, and it
#: leaves ~32 KB for the difference between their serializer and ours.
#:
#: Raising a buffer on the READING side cannot help. That was tried first --
#: 1 MB through 32 MB, every one returning zero.
TIMELINE_SERIALIZE_BUDGET = 1024 * 1024

# Automatic Timeline sharding is intentionally parked for now.  The retained
# implementation below can be re-enabled after the listener-fanout design has
# contributor approval and in-game acceptance coverage.  Keeping this as an
# explicit gate, rather than deleting or commenting out the implementation,
# leaves the single-Timeline production behavior unambiguous and the dormant
# path executable in tests.
ENABLE_TIMELINE_SHARDING = False


def installed_event_is_looping(name: str):
    """Loop metadata for an exact installed Play event, when available.

    Kept in the orchestration layer so the independently usable MIDI parser
    does not import upward into the optional installed-game audio subsystem.
    """
    try:
        from snapmap_midi.audio import library

        return library.event_is_looping(name)
    except Exception:
        return None


def installed_event_duration_ms(name: str):
    """Installed non-looping event duration, when soundbank metadata has one."""
    try:
        from snapmap_midi.audio import library

        return library.event_duration_ms(name)
    except Exception:
        return None


def _timeline_self_ref(entity: dict) -> str:
    """The entity reference a Timeline's own empty event group carries."""
    return entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["entity"]


def _set_single_timeline_group(entity: dict, target_id: str, events) -> None:
    """Make one Timeline schedule one event list against ``target_id``."""
    entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = {
        "item[0]": {"entity": target_id, "events": _events.events_block(events)},
        "num": 1,
    }


def _layout_song_timelines(doc: SnapMapDocument, switch_uid: int, timelines) -> None:
    """Put the master and auxiliary Unknowns after the song interactive."""

    switch = doc.find_entity(switch_uid)
    spawn = switch["entityDef"]["state"]["edit"].get("spawnPosition", {}) or {}
    anchor = (spawn.get("x", 0.0), spawn.get("y", 0.0), spawn.get("z", 0.0))
    seen = set()
    ordered = []
    for entity in timelines:
        uid = entity["uniqueId"]
        if uid not in seen:
            seen.add(uid)
            ordered.append(entity)
    for index, entity in enumerate(ordered):
        x, y, z = timeline_position_after_interactive(anchor, index)
        entity["entityDef"]["state"]["edit"]["spawnPosition"] = {
            "x": x,
            "y": y,
            "z": z,
        }


def _event_time_batches(events):
    """Adjacent equal-time events, kept atomic when a Timeline is sharded.

    Modifier-before-start order is load-bearing. Splitting two events at the
    same timestamp into separately triggered Timelines would hand their order
    back to the engine scheduler, so every equal-time batch stays together.
    """
    batches = []
    for event in events:
        if not batches or batches[-1][0]["eventTime"] != event["eventTime"]:
            batches.append([])
        batches[-1].append(event)
    return batches


def _write_timeline_shards(
    doc: SnapMapDocument,
    primary: dict,
    target_id: str,
    events,
    display_name: str,
):
    """Store events across editor-safe Timeline entities.

    The first shard is the existing sound emitter itself. Additional entities
    are schedulers targeting that same emitter, so sharding changes only where
    event data is stored; it does not create another audible voice or break
    pitch state. Returns ``[(entity, trigger_reference), ...]``.
    """
    batches = _event_time_batches(events)
    shards = []
    entity = primary
    trigger_ref = _timeline_self_ref(entity)
    chunk = []
    shard_index = 0

    if not batches:
        _set_single_timeline_group(entity, target_id, [])
        return [(entity, trigger_ref)]

    for batch in batches:
        candidate = chunk + batch
        _set_single_timeline_group(entity, target_id, candidate)
        if chunk and len(serialize(entity)) > TIMELINE_SERIALIZE_BUDGET:
            _set_single_timeline_group(entity, target_id, chunk)
            shards.append((entity, trigger_ref))
            shard_index += 1
            entity = doc.add_timeline()
            entity["displayName"] = "%s-s%d" % (display_name, shard_index)
            trigger_ref = _timeline_self_ref(entity)
            chunk = list(batch)
            _set_single_timeline_group(entity, target_id, chunk)
        else:
            chunk = candidate
    shards.append((entity, trigger_ref))
    return shards


def compile_to_rawmap(
    mid_path,
    baseline_bytes: Optional[bytes] = None,
    button_name: str = "snapmap-midi-song",
    family_overrides: Optional[dict] = None,
    drums="auto",
    max_speakers: int = 32,
    release_s: float = 0.1,
    hard_stop: bool = False,
    max_events: Optional[int] = None,
    drop_sustain_over_ms: Optional[int] = None,
    min_sustain_ms: Optional[int] = None,
    drop_shaders: Optional[set] = None,
    cap_sustain_ms: Optional[int] = None,
    bass_pitch: int = 78,
    bass_cap_ms: Optional[int] = None,
    max_poly: Optional[int] = None,
    song_polyphony: int = 32,
    part_voices: Optional[dict] = None,
    part_polyphony: Optional[dict] = None,
    part_glide_ms: Optional[dict] = None,
    part_attack_ms: Optional[dict] = None,
    part_release_s: Optional[dict] = None,
    part_hard_stop: Optional[dict] = None,
    part_sustain_ms: Optional[dict] = None,
    decaying_families: Optional[set] = None,
    family_caps: Optional[dict] = None,
    channel_families: Optional[dict] = None,
    low_split=None,
    drum_overrides: Optional[dict] = None,
    note_index=None,
    channel_mutes: Optional[set] = None,
    drum_key_overrides: Optional[dict] = None,
    channel_solos: Optional[set] = None,
    channel_sounds: Optional[dict] = None,
    channel_pitch_profiles: Optional[dict] = None,
    part_percussion: Optional[dict] = None,
    note_overrides: Optional[dict] = None,
    part_volume_db: Optional[dict] = None,
    master_volume_db: int = 0,
):
    """Compile a MIDI file into finished map bytes plus a statistics summary.

    `baseline_bytes` is optional. Omit it and the song is staged in a blank
    room authored from nothing; pass a saved map and the song is added to it,
    reusing that map's timeline if it has one.

    ``button_name`` remains accepted for API compatibility, but MIDI exports
    always label their interactive with ``mid_path``'s filename so a probe or
    stale sidecar name cannot leak into a later song.

    Channel mute/solo state and drum-key overrides are handed straight to
    `parse_notes`; all are inert when empty, which lets the workstation pass
    them on every compile without moving a byte.
    """
    data = blank_map() if baseline_bytes is None else json.loads(baseline_bytes)
    doc = SnapMapDocument(data=data, palette_refs=PRODUCT_PALETTE_REFS)
    timeline = ensure_timeline(doc)
    timeline_id = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
        "item[0]"
    ]["entity"]

    notes, stats = parse_notes(
        mid_path,
        drums,
        family_overrides,
        decaying_families,
        channel_families,
        low_split,
        drum_overrides,
        note_index=note_index,
        channel_mutes=channel_mutes,
        drum_key_overrides=drum_key_overrides,
        channel_solos=channel_solos,
        channel_sounds=channel_sounds,
        event_is_looping=installed_event_is_looping,
        channel_pitch_profiles=channel_pitch_profiles,
        part_percussion=part_percussion,
        note_overrides=note_overrides,
        part_volume_db=part_volume_db,
        master_volume_db=master_volume_db,
    )
    decaying = [n for n in notes if not n.sustained]
    sustained = [n for n in notes if n.sustained]

    if drop_sustain_over_ms is not None:
        sustained = [n for n in sustained if n.duration <= drop_sustain_over_ms]
    if min_sustain_ms:
        # Rapid ornaments churn emitter slots harder than anything else.
        sustained = [n for n in sustained if n.duration >= min_sustain_ms]
    if drop_shaders:
        decaying = [n for n in decaying if n.shader not in drop_shaders]
    decaying.sort(key=lambda n: (n.start, n.chan, n.source_pitch, n.id))
    if max_events:
        decaying = decaying[:max_events]

    part_voices = part_voices or {}
    part_polyphony = part_polyphony or {}
    parts = {}
    for note in decaying + sustained:
        parts.setdefault((getattr(note, "track", 0), note.chan), []).append(note)
    limited_notes = []
    for part_key in sorted(parts):
        track, channel = part_key
        part = parts[part_key]
        poly = for_part(part_polyphony, track, channel, max_poly)
        limited_notes.extend(thin_polyphony(part, poly) if poly else part)
    limited_notes = thin_global_polyphony(limited_notes, song_polyphony)
    decaying = [note for note in limited_notes if not note.sustained]
    sustained = [note for note in limited_notes if note.sustained]

    shared_decaying, expressive_decaying, layers = prepare_voice_layers(
        decaying,
        sustained,
        cap_sustain_ms=cap_sustain_ms,
        bass_pitch=bass_pitch,
        bass_cap_ms=bass_cap_ms,
        family_caps=family_caps,
        duration_lookup=installed_event_duration_ms,
        part_glide_ms=part_glide_ms,
        part_attack_ms=part_attack_ms,
        part_voices=part_voices,
        part_sustain_ms=part_sustain_ms,
    )
    shared_events = sorted(
        (
            _events.start(n.shader, n.start, channel=_events.LAYERED_CHANNEL)
            for n in shared_decaying
        ),
        key=lambda e: e["eventTime"],
    )
    groups = [(timeline_id, shared_events)]
    timeline_by_target = {timeline_id: timeline}

    voices_used = 0
    peak_voices = 0
    isolated = []
    for part_key in sorted(layers):
        track, channel = part_key
        layer = layers[part_key]
        voices = for_part(part_voices, track, channel, max_speakers)
        layer = apply_voice_cap(layer, voices)
        isolated.extend(layer)

    # Voices are one song-wide pool.  Polyphony remains a per-track editorial
    # choice, but a global voice count must author no more than this many
    # dedicated pitch-controlled emitters across the entire arrangement.
    isolated = thin_simultaneous(isolated, max_speakers)
    count = allocate_voices(isolated, max_speakers)
    apply_glides(isolated, part_glide_ms)
    voices_used = peak_voices = count

    by_voice = {}
    for n in isolated:
        by_voice.setdefault(n.voice, []).append(n)

    for voice in range(count):
        voice_notes = sorted(by_voice.get(voice, []), key=lambda n: n.start)
        emitter = doc.add_timeline()
        emitter["displayName"] = "snapmap-midi-v%d" % voice
        emitter_id = _timeline_self_ref(emitter)
        timeline_by_target[emitter_id] = emitter

        scheduled = []
        for i, n in enumerate(voice_notes):
            glide_ms = int(getattr(n, "glide_ms", 0) or 0)
            start_pitch = (
                getattr(n, "glide_from_pitch") if glide_ms else n.pitch_modifier
            )
            # Live-engine probes established that an instantaneous modifier has
            # to be serialized BEFORE the same-time start. Speaker entities
            # swallow this path; an ordinary Timeline target applies it. Every
            # isolated note writes an explicit pitch and gain, including zero,
            # so a reused emitter cannot inherit the previous note's state.
            scheduled.append(_events.fade_pitch(n.start, start_pitch))
            attack_ms = int(
                for_part(part_attack_ms or {}, getattr(n, "track", 0), n.chan, 0) or 0
            )
            # The game does not carry a fade state into a subsequently
            # started one-shot. Start on the exact MIDI time, then address the
            # live sound one millisecond later with a mute and one millisecond
            # after that with its gain ramp. That keeps the attack targeted at
            # an existing engine sound without shifting the arrangement.
            sound_start = n.start
            post_start = sound_start + 1
            if attack_ms:
                scheduled.append(_events.start(n.shader, sound_start))
                scheduled.append(_events.fade(post_start, -60.0, 0.0))
                scheduled.append(_events.fade(post_start + 1, n.volume_db, attack_ms / 1000.0))
            else:
                scheduled.append(_events.fade(n.start, n.volume_db, 0.0))
                scheduled.append(_events.start(n.shader, sound_start))
            if glide_ms:
                # One millisecond keeps the ramp on the newly started sound.
                # Zero-delay pitch-before-start is the separate immediate path
                # proven above; longer onset delays were audibly inconsistent.
                scheduled.append(
                    _events.fade_pitch(
                        post_start,
                        n.pitch_modifier,
                        glide_ms / 1000.0,
                    )
                )
            following = voice_notes[i + 1] if i + 1 < len(voice_notes) else None
            voice_cap_end = getattr(n, "voice_cap_end", None)
            stop_at = voice_cap_end if voice_cap_end is not None else n.end
            # Decaying sounds end on their own. Sustains, and one-shots with
            # an explicit Sustain Limit, stop only before a gap; a following
            # start on the same emitter is already the correct cutoff for
            # legato or a stolen voice. A track cap can steal a note even when
            # the global allocator chose another emitter, so it gets an
            # explicit hard stop at its virtual cutoff.
            if voice_cap_end is not None and (following is None or following.start > stop_at):
                scheduled.append(_events.stop(stop_at))
            elif (
                (n.sustained or getattr(n, "sustain_limited", False))
                and (following is None or following.start > n.end)
            ):
                note_release = for_part(
                    part_release_s or {},
                    getattr(n, "track", 0),
                    n.chan,
                    release_s,
                )
                note_hard_stop = for_part(
                    part_hard_stop or {},
                    getattr(n, "track", 0),
                    n.chan,
                    hard_stop,
                )
                scheduled.append(
                    _events.stop(n.end)
                    if note_hard_stop
                    else _events.fade(n.end, -60.0, note_release)
                )
        groups.append((emitter_id, sorted(scheduled, key=lambda e: e["eventTime"])))

    entity_events = {
        "item[%d]" % i: {"entity": eid, "events": _events.events_block(evs)}
        for i, (eid, evs) in enumerate(groups)
    }
    entity_events["num"] = len(groups)
    timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = entity_events

    # Production currently retains one master Timeline and one trigger target:
    # fewer targets and one place to inspect the arrangement. The parked branch
    # below can distribute an oversized master after listener fanout receives
    # contributor approval. Speaker entities never helped this limit because
    # all their events still lived inside the master Timeline.
    unsharded_timeline_bytes = len(serialize(timeline))
    activated_timelines = [(timeline, timeline_id)]
    if ENABLE_TIMELINE_SHARDING and unsharded_timeline_bytes > TIMELINE_SERIALIZE_BUDGET:
        activated_timelines = []
        for target_id, scheduled in groups:
            primary = timeline_by_target[target_id]
            display_name = primary.get("displayName") or "snapmap-midi-shared"
            activated_timelines.extend(
                _write_timeline_shards(
                    doc,
                    primary,
                    target_id,
                    scheduled,
                    display_name,
                )
            )

    trigger_ids = [trigger_ref for _entity, trigger_ref in activated_timelines]
    timeline_sizes = [len(serialize(entity)) for entity, _ref in activated_timelines]
    song_name = Path(mid_path).name
    switch_uid = add_button(doc, trigger_ids, song_name)
    layout_entities = list(timeline_by_target.values())
    layout_entities.extend(entity for entity, _trigger_ref in activated_timelines)
    _layout_song_timelines(doc, switch_uid, layout_entities)

    stats.update(
        {
            "notes": len(notes),
            "decaying": len(decaying),
            "sustained": len(sustained),
            "voices": voices_used,
            "events": sum(len(e) for _, e in groups),
            "shared_one_shots": len(shared_decaying),
            "expressive_notes": len(sustained) + len(expressive_decaying),
            "expressive_one_shots": len(expressive_decaying),
            "expressive_voices": voices_used,
            "long_sustains": sum(1 for n in sustained if n.duration > 1000),
            "peak_voices": peak_voices,
            "max_speakers": max_speakers,
            # The editor buffer is per Timeline entity. ``timeline_bytes``
            # remains the warning-compatible maximum; the total explains why a
            # large map may contain several individually safe shards.
            "timeline_bytes": max(timeline_sizes, default=0),
            "timeline_total_bytes": sum(timeline_sizes),
            "timeline_unsharded_bytes": unsharded_timeline_bytes,
            "timeline_shards": len(activated_timelines),
            "timeline_budget": TIMELINE_SERIALIZE_BUDGET,
            "timeline_sharding_enabled": ENABLE_TIMELINE_SHARDING,
        }
    )
    return serialize(doc.data), stats
