"""Orchestration: a MIDI file becomes a playable map.

Scheduling follows expression and decay independently:

  - Neutral decaying notes layer polyphonically on the shared Timeline entity.
  - Decaying notes with pitch or gain use isolated, duration-reserved speakers
    and are left to fade on their own.
  - Sustained notes use isolated speakers plus explicit stops or releases.

Voice preparation is shared with browser preview and allocation stays per MIDI
channel, so one instrument cannot steal another channel's voice. Density
controls reduce exposure to the engine's emitter-recycling limit; per-note
pitch and volume controls describe expression and do not change that limit.
"""

from __future__ import annotations

import json
from typing import Optional

from snapmap_midi.music.midi import parse_notes
from snapmap_midi.music.voices import (
    allocate_voices,
    prepare_voice_layers,
    thin_polyphony,
)
from snapmap_midi.rawmap import template
from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SPEAKER_INHERIT, SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map
from snapmap_midi.sound import events as _events
from snapmap_midi.sound.timeline import add_button, ensure_timeline


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
    master_volume_db: int = 0,
):
    """Compile a MIDI file into finished map bytes plus a statistics summary.

    `baseline_bytes` is optional. Omit it and the song is staged in a blank
    room authored from nothing; pass a saved map and the song is added to it,
    reusing that map's timeline if it has one.

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

    shared_decaying, expressive_decaying, layers = prepare_voice_layers(
        decaying,
        sustained,
        cap_sustain_ms=cap_sustain_ms,
        bass_pitch=bass_pitch,
        bass_cap_ms=bass_cap_ms,
        family_caps=family_caps,
        duration_lookup=installed_event_duration_ms,
    )
    shared_events = sorted(
        (
            _events.start(n.shader, n.start, channel=_events.LAYERED_CHANNEL)
            for n in shared_decaying
        ),
        key=lambda e: e["eventTime"],
    )
    groups = [(timeline_id, shared_events)]

    module = doc.module_stem()

    voices_used = 0
    peak_voices = 0
    speaker_index = 0
    # A speaker's name carries the track only when the channel needs it to stay
    # unique. One part per channel is the ordinary case and keeps the name it
    # has always had, so maps that were byte-identical before still are.
    parts_per_channel: dict = {}
    for _track, _chan in layers:
        parts_per_channel[_chan] = parts_per_channel.get(_chan, 0) + 1
    for part_key in sorted(layers):
        track, channel = part_key
        layer = layers[part_key]
        if max_poly:
            layer = thin_polyphony(layer, max_poly)
        count = allocate_voices(layer, max_speakers)
        voices_used += count
        # Voices are allocated per layer against max_speakers, so the running
        # total can pass it while no single layer is anywhere near it. The
        # worst layer is the one that says whether anything was thinned.
        peak_voices = max(peak_voices, count)

        by_voice = {}
        for n in layer:
            by_voice.setdefault(n.voice, []).append(n)

        for voice in range(count):
            voice_notes = sorted(by_voice.get(voice, []), key=lambda n: n.start)
            uid = doc.add_speaker(
                sound=(voice_notes[0].shader if voice_notes else ""),
                position=template.speaker_position(speaker_index),
                display_name=(
                    "snapmap-midi-ch%d-v%d" % (channel, voice)
                    if parts_per_channel.get(channel, 1) < 2
                    else "snapmap-midi-ch%d-t%d-v%d" % (channel, track, voice)
                ),
            )
            speaker_id = "0_{}/{}_{}".format(module, SPEAKER_INHERIT, uid)
            speaker_index += 1

            scheduled = []
            for i, n in enumerate(voice_notes):
                scheduled.append(_events.start(n.shader, n.start))
                if n.pitch_modifier:
                    scheduled.append(_events.fade_pitch(n.start, n.pitch_modifier))
                if n.volume_db:
                    scheduled.append(_events.fade(n.start, n.volume_db, 0.0))
                following = voice_notes[i + 1] if i + 1 < len(voice_notes) else None
                # Decaying sounds end on their own. Sustains stop only before a
                # gap; a following start on the same speaker is already the
                # correct cutoff for legato or a stolen voice.
                if n.sustained and (following is None or following.start > n.end):
                    scheduled.append(
                        _events.stop(n.end) if hard_stop else _events.fade(n.end, -60.0, release_s)
                    )
            groups.append((speaker_id, sorted(scheduled, key=lambda e: e["eventTime"])))

    entity_events = {
        "item[%d]" % i: {"entity": eid, "events": _events.events_block(evs)}
        for i, (eid, evs) in enumerate(groups)
    }
    entity_events["num"] = len(groups)
    timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"] = entity_events

    add_button(doc, timeline_id, button_name)

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
        }
    )
    return serialize(doc.data), stats
