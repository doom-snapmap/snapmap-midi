"""Orchestration: a MIDI file plus a baseline map becomes a playable map.

The arrangement splits in two, because the two halves have to be scheduled
differently:

  - Decaying sounds and drums are one-shots. They layer polyphonically on the
    timeline entity itself and are never stopped, because they fade on their
    own and could not be stopped reliably anyway.
  - Sustained notes hold at full volume, so each gets a speaker voice it can
    be stopped on. Voices are allocated PER LAYER, so one instrument can never
    steal another's voice or cut it off mid-phrase.

The tuning levers all exist for one reason: the engine recycles sound emitter
slots under load, and a note whose slot is recycled can no longer be stopped,
so it rings its entire sample and smears into the next phrase. Every lever is
a different way to reduce how many sounds are live at once.
"""

from __future__ import annotations

import json
from typing import Optional

from snapmap_midi.music.midi import parse_notes
from snapmap_midi.music.voices import allocate_voices, thin_polyphony
from snapmap_midi.rawmap.codec import serialize
from snapmap_midi.rawmap.document import SPEAKER_INHERIT, SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map
from snapmap_midi.sound import events as _events
from snapmap_midi.sound.palette import shader_pitch
from snapmap_midi.sound.timeline import add_button, find_timeline


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
):
    """Compile a MIDI file into finished map bytes plus a statistics summary.

    `baseline_bytes` is optional. Omit it and the song is staged in a blank
    room authored from nothing; pass a saved map and the song is added to it,
    reusing that map's timeline if it has one.
    """
    data = blank_map() if baseline_bytes is None else json.loads(baseline_bytes)
    doc = SnapMapDocument(data=data, palette_refs=PRODUCT_PALETTE_REFS)
    timeline = find_timeline(doc)
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

    # Keep every note, but bound how long each holds a voice. Low notes stack
    # many deep and drive concurrency, so they are capped hardest; high
    # melodic notes barely stack and are left alone.
    if cap_sustain_ms or bass_cap_ms or family_caps:
        family_caps = family_caps or {}
        for n in sustained:
            cap = family_caps.get(n.fam, cap_sustain_ms or 10**9)
            pitch = shader_pitch(n.shader)
            if bass_cap_ms and pitch is not None and pitch < bass_pitch:
                cap = min(cap, bass_cap_ms)
            if n.duration > cap:
                n.end = n.start + cap

    # Group 0: one-shots on the timeline entity itself. These layer on ONE
    # entity, so they must start unbound -- a concrete channel would make the
    # entity monophonic per channel and the layers would cut each other off.
    decaying_events = sorted(
        (_events.start(n.shader, n.start, channel=_events.LAYERED_CHANNEL) for n in decaying),
        key=lambda e: e["eventTime"],
    )
    if max_events:
        decaying_events = decaying_events[:max_events]
    groups = [(timeline_id, decaying_events)]

    module = doc.module_stem()

    # Per-layer voice allocation: each MIDI channel gets its own speakers,
    # sized to that layer's own polyphony. Layers never steal from each other
    # and can be tuned independently. A single global pool mixed every
    # instrument onto shared speakers and cut phrases off across layers.
    layers = {}
    for n in sustained:
        layers.setdefault(n.chan, []).append(n)

    voices_used = 0
    speaker_index = 0
    for channel in sorted(layers):
        layer = layers[channel]
        if max_poly:
            layer = thin_polyphony(layer, max_poly)
        count = allocate_voices(layer, max_speakers)
        voices_used += count

        by_voice = {}
        for n in layer:
            by_voice.setdefault(n.voice, []).append(n)

        for voice in range(count):
            voice_notes = sorted(by_voice.get(voice, []), key=lambda n: n.start)
            uid = doc.add_speaker(
                sound=(voice_notes[0].shader if voice_notes else ""),
                position=(float(120 + 24 * speaker_index), 0.0, 64.0),
                display_name="claude-ch%d-v%d" % (channel, voice),
            )
            speaker_id = "0_{}/{}_{}".format(module, SPEAKER_INHERIT, uid)
            speaker_index += 1

            scheduled = []
            for i, n in enumerate(voice_notes):
                scheduled.append(_events.start(n.shader, n.start))
                following = voice_notes[i + 1] if i + 1 < len(voice_notes) else None
                # Stop only before a GAP. For legato notes the next start
                # already stops this one, and emitting a stop there would
                # instead kill the note that just began on the same speaker.
                if following is None or following.start > n.end:
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
        }
    )
    return serialize(doc.data), stats
