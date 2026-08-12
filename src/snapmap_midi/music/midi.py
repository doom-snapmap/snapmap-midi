"""MIDI parsing: pair note-on with note-off, and decide what each note plays.

A MIDI file streams events; the compiler needs notes with a start and an end.
Pairing is per (channel, pitch) and stacked, because the same pitch can be
retriggered on a channel before the first one ends.

A note that never receives its note-off is held to the end of the song rather
than dropped. That is the honest reading: the note was still sounding when the
file ran out.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from snapmap_midi.music.expression import annotate, expression_for
from snapmap_midi.music.gm import DRUM_CHANNEL, DRUM_MAP, SUSTAINED, gm_to_family
from snapmap_midi.sound import palette


@dataclass
class Note:
    """One paired note.

    Field order is deliberate and load-bearing. Anything derived from this
    record is serialized in declaration order, and the map format preserves
    key order rather than sorting, so reordering these fields changes output
    bytes with no semantic change whatsoever.
    """

    start: int
    end: int
    shader: str
    sustained: bool
    chan: int
    fam: str
    voice: Optional[int] = None

    @property
    def duration(self) -> int:
        return self.end - self.start


def channel_is_percussion(mid, drum_map=DRUM_MAP) -> bool:
    """Guess whether the percussion channel really carries a kit.

    Some files put a melodic part on the percussion channel, and some put a
    real kit elsewhere. The heuristic: a genuine kit uses few distinct keys
    and most of them are keys we recognise.
    """
    total, recognised, pitches = 0, 0, set()
    for msg in mid:
        if msg.type == "note_on" and msg.velocity > 0 and msg.channel == DRUM_CHANNEL:
            total += 1
            pitches.add(msg.note)
            if msg.note in drum_map:
                recognised += 1
    return total > 0 and len(pitches) <= 20 and recognised / total >= 0.6


def _exact_sound_sustained(
    shader: str, family: str, no_sustain, event_is_looping, event_looping_cache
) -> bool:
    """Whether an exact assignment needs a paired stop event.

    Palette sounds retain their established family behavior. For a full-game
    event, installed catalog metadata decides. An unknown manually entered Play
    event is treated as looping because failing to stop a loop leaks an emitter,
    while stopping a one-shot that already ended is harmless.
    """
    if family != "exact":
        return (family in SUSTAINED or family.startswith("amb_")) and family not in no_sustain
    if shader not in event_looping_cache:
        try:
            event_looping_cache[shader] = (
                event_is_looping(shader) if event_is_looping is not None else None
            )
        except Exception:
            event_looping_cache[shader] = None
    return event_looping_cache[shader] is not False


def parse_notes(
    mid_path,
    drums="auto",
    family_overrides=None,
    decaying_families=None,
    channel_families=None,
    low_split=None,
    drum_overrides=None,
    note_index=None,
    channel_mutes=None,
    drum_key_overrides=None,
    channel_solos=None,
    channel_sounds=None,
    event_is_looping=None,
    channel_pitch_profiles=None,
    note_overrides=None,
    master_volume_db=0,
    include_silent=False,
):
    """Parse a MIDI file into paired notes plus a statistics summary.

    Family selection runs in increasing order of specificity: the program's
    default family, then a family-wide override, then a per-channel override,
    then a pitch split that sends the low register somewhere else. The last
    one to apply wins.

    `channel_mutes` silences whole channels. When any channel is in
    `channel_solos`, only soloed, unmuted channels are audible; mute wins when
    both switches are set. Silent notes are not counted in `dropped` because
    they were excluded deliberately rather than lost by the palette. The UI
    may set `include_silent` to retain those notes for a dimmed piano-roll
    display, while preview audio and map export use only notes whose `audible`
    metadata is true.

    `drum_key_overrides` gives a percussion key its sound by MIDI key number,
    which is the only lever that reaches the exotic keys `DRUM_MAP` drops on
    purpose. It is keyed by key rather than by shader precisely so it can name
    a key that currently resolves to nothing at all.
    """
    import mido

    family_overrides = family_overrides or {}
    drum_overrides = drum_overrides or {}
    drum_key_overrides = drum_key_overrides or {}
    channel_families = channel_families or {}
    channel_sounds = channel_sounds or {}
    channel_mutes = channel_mutes or frozenset()
    channel_pitch_profiles = channel_pitch_profiles or {}
    note_overrides = note_overrides or {}
    no_sustain = set(decaying_families or ())
    channel_solos = channel_solos or frozenset()
    event_looping_cache = {}
    low_cut, low_family = low_split or (0, None)
    sound_categories = palette.sound_categories()

    # clip=True clamps out-of-range data bytes rather than refusing the file.
    mid = mido.MidiFile(str(mid_path), clip=True)
    index = note_index if note_index is not None else palette.build_note_index()
    drums_on = channel_is_percussion(mid) if drums == "auto" else bool(drums)

    program = {}
    active = defaultdict(list)  # (channel, pitch) -> [pending starts]
    notes: list[Note] = []
    dropped = 0
    occurrences = defaultdict(int)
    elapsed = 0.0

    for msg in mid:
        elapsed += msg.time
        now = int(elapsed * 1000)
        if msg.type == "program_change":
            program[msg.channel] = msg.program
        elif msg.type == "note_on" and msg.velocity > 0:
            occurrence_key = (msg.channel, msg.note)
            occurrences[occurrence_key] += 1
            note_id = "%d:%d:%d" % (
                msg.channel,
                msg.note,
                occurrences[occurrence_key],
            )
            muted = msg.channel in channel_mutes
            solo_excluded = bool(channel_solos and msg.channel not in channel_solos)
            audible = not muted and not solo_excluded
            if not audible and not include_silent:
                continue
            override = note_overrides.get(note_id, {})
            pitch_offset = int(override.get("pitch_offset", 0))
            note_volume_db = int(override["volume_db"]) if "volume_db" in override else None
            volume_trim_db = int(override.get("volume_trim_db", 0))
            exact_sound = channel_sounds.get(msg.channel)
            chosen_family = channel_families.get(msg.channel)
            applied_root = None
            profile_root = None
            root_confidence = None
            root_source = None
            pitch_follow = False
            if exact_sound is not None:
                shader = exact_sound
                family = sound_categories.get(shader, "exact")
                profile = channel_pitch_profiles.get(msg.channel, {})
                profile_root = profile.get("root_midi")
                root_confidence = profile.get("root_confidence")
                root_source = profile.get("root_source")
                pitch_follow = bool(profile.get("pitch_follow", False) and profile_root is not None)
                if pitch_follow:
                    applied_root = float(profile_root)
                # Full-game exact events take their loop behavior from the
                # installed event catalog. Curated palette assignments preserve
                # the established family scheduling rules.
                sustained = _exact_sound_sustained(
                    shader,
                    family,
                    no_sustain,
                    event_is_looping,
                    event_looping_cache,
                )
            elif chosen_family is not None:
                # A pitched family selected for channel 10 is still a pitched
                # instrument. The explicit track choice wins over automatic
                # percussion detection, so drums need no separate workspace.
                family = chosen_family
                shader = palette.decl_for(family, msg.note, index)
                sustained = family in SUSTAINED and family not in no_sustain
            elif msg.channel == DRUM_CHANNEL and drums_on:
                # The per-key choice is the user's and is final. `drum_overrides`
                # is keyed by resolved shader and exists to retimbre what the
                # TABLE picked, so applying it after a per-key override would
                # silently replace the sound someone had just chosen.
                shader = drum_key_overrides.get(msg.note)
                if shader is None:
                    shader = DRUM_MAP.get(msg.note)
                    if shader:
                        shader = drum_overrides.get(shader, shader)
                sustained, family = False, "drums"
            else:
                family = gm_to_family(program.get(msg.channel, 0))
                family = family_overrides.get(family, family)
                if low_family and msg.note < low_cut:
                    family = low_family
                shader = palette.decl_for(family, msg.note, index)
                sustained = family in SUSTAINED and family not in no_sustain
            if shader:
                if exact_sound is None and family != "drums":
                    profile_root = palette.shader_pitch(shader)
                    if profile_root is not None:
                        applied_root = float(profile_root)
                        root_confidence = 1.0
                        root_source = "palette_name"
                        pitch_follow = True
                expression = expression_for(
                    msg.note,
                    msg.velocity,
                    applied_root,
                    pitch_offset=pitch_offset,
                    volume_trim_db=volume_trim_db,
                    note_volume_db=note_volume_db,
                    master_volume_db=master_volume_db,
                )
                metadata = {
                    "id": note_id,
                    "profile_root_pitch": profile_root,
                    "root_confidence": root_confidence,
                    "root_source": root_source,
                    "pitch_follow": pitch_follow,
                    "audible": audible,
                    "muted": muted,
                    "solo_excluded": solo_excluded,
                }
                active[(msg.channel, msg.note)].append(
                    (now, shader, sustained, family, expression, metadata)
                )
            else:
                if audible:
                    dropped += 1
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            pending = active.get((msg.channel, msg.note))
            if pending:
                started, shader, sustained, family, expression, metadata = pending.pop(0)
                note = Note(started, now, shader, sustained, msg.channel, family)
                notes.append(annotate(note, expression, **metadata))

    end = int(elapsed * 1000)
    for (channel, pitch), pending in active.items():
        for started, shader, sustained, family, expression, metadata in pending:
            # Still sounding when the file ended; hold it rather than drop it.
            note = Note(started, end, shader, sustained, channel, family)
            notes.append(annotate(note, expression, **metadata))

    audible_notes = [note for note in notes if getattr(note, "audible", True)]
    pitch_limits = {}
    for note in audible_notes:
        if not note.pitch_limited:
            continue
        detail = pitch_limits.setdefault(
            note.chan,
            {
                "channel": note.chan,
                "count": 0,
                "source_low": note.source_pitch,
                "source_high": note.source_pitch,
                "requested_low": note.requested_pitch,
                "requested_high": note.requested_pitch,
                "applied_low": note.pitch_modifier,
                "applied_high": note.pitch_modifier,
            },
        )
        detail["count"] += 1
        detail["source_low"] = min(detail["source_low"], note.source_pitch)
        detail["source_high"] = max(detail["source_high"], note.source_pitch)
        detail["requested_low"] = min(detail["requested_low"], note.requested_pitch)
        detail["requested_high"] = max(detail["requested_high"], note.requested_pitch)
        detail["applied_low"] = min(detail["applied_low"], note.pitch_modifier)
        detail["applied_high"] = max(detail["applied_high"], note.pitch_modifier)

    stats = {
        "drums_on": drums_on,
        "dropped": dropped,
        "duration_s": round(elapsed, 2),
        "pitch_adjusted": sum(note.pitch_modifier != 0 for note in audible_notes),
        "volume_adjusted": sum(note.volume_db != 0 for note in audible_notes),
        "pitch_limited": sum(note.pitch_limited for note in audible_notes),
        "pitch_limit_channels": [pitch_limits[channel] for channel in sorted(pitch_limits)],
        "volume_limited": sum(note.volume_limited for note in audible_notes),
    }
    return notes, stats
