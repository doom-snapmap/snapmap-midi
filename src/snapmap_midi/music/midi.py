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
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional

from snapmap_midi.music.expression import annotate, expression_for
from snapmap_midi.music.gm import DRUM_CHANNEL, SUSTAINED, drum_table, gm_to_family
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


def messages_with_tracks(mid):
    """mido's own merge, except each message keeps the track it came from.

    `MidiFile.__iter__` merges the tracks and discards which one each message
    came from. That single omission is why two parts written as separate tracks
    collapsed into one whenever they shared a MIDI channel: by the time the
    first note was paired, the only identity left was `msg.channel`.

    This reproduces mido's merge exactly -- each track to absolute ticks, one
    stable sort so ties keep track order, then ticks to seconds against the
    running tempo -- and yields `(track_index, message, elapsed_seconds)`.
    Tempo is applied after the message that changes it, as mido does, so a
    `set_tempo` governs what follows it rather than the gap before it.

    Type 2 files are refused for the same reason mido refuses them: their tracks
    are asynchronous, so there is no shared clock to merge them onto.
    """
    import mido

    if mid.type == 2:
        raise TypeError("can't merge tracks in a type 2 (asynchronous) MIDI file")

    tagged = []
    for index, track in enumerate(mid.tracks):
        now = 0
        for message in track:
            now += message.time
            tagged.append((now, index, message))
    tagged.sort(key=lambda item: item[0])

    tempo = 500_000
    elapsed = 0.0
    previous = 0
    for tick, index, message in tagged:
        elapsed += mido.tick2second(tick - previous, mid.ticks_per_beat, tempo)
        previous = tick
        yield index, message, elapsed
        if message.type == "set_tempo":
            tempo = message.tempo


def for_part(mapping, track, channel, default=None):
    """The most specific setting for one part.

    Every per-channel lever accepts two kinds of key. A `(track, channel)` pair
    names one part and wins. A bare channel number is the wildcard: it applies to
    every part on that channel, which is both what a settings document written
    before parts existed means and what a user who never split a channel expects.

    Keeping the wildcard rather than expanding it is what lets those documents
    load untouched -- there is no list of parts at the moment settings are
    validated, only at the moment a note is resolved, which is here.
    """
    if (track, channel) in mapping:
        return mapping[(track, channel)]
    return mapping.get(channel, default)


def in_part(collection, track, channel) -> bool:
    """Whether a per-part switch is on for this part.

    A SET names only the parts a switch is on for, which cannot express "this
    part specifically is off" -- so a named part could never beat a channel-wide
    entry, and un-muting one part of a muted channel was impossible to say. A
    MAPPING of selector to boolean can say it, and `to_compile_kwargs` sends
    one.

    Sets stay accepted: they are the library API's own spelling and the natural
    way to put it when nothing is being overridden.
    """
    if isinstance(collection, Mapping):
        return bool(for_part(collection, track, channel, False))
    return (track, channel) in collection or channel in collection


def _switch_is_used(collection) -> bool:
    """Whether any part has this switch on. Solo is only in force when one is."""
    if isinstance(collection, Mapping):
        return any(collection.values())
    return bool(collection)


def is_percussion_part(modes, track, channel, drums_on: bool) -> bool:
    """Whether this part is a drum kit.

    `auto` is the General MIDI convention -- channel 10, if the heuristic
    accepted it as a kit -- and is right for nearly every file. A part may
    also say outright which it is, because the convention is only a
    convention: a composer may write a kit to channel 6, and before this
    existed those notes were mapped as piano and nothing said so.

    The heuristic is deliberately NOT extended to other channels. Its keys
    span B1 to F5, which is exactly where bass lines sit, so a sparse bass
    part would qualify as a kit and be turned into drums with no warning.
    """
    mode = for_part(modes, track, channel, "auto")
    if mode == "kit":
        return True
    if mode == "melodic":
        return False
    return channel == DRUM_CHANNEL and drums_on


def _record(note):
    """Freeze the note's written length before any scheduling policy touches it.

    `note.end` is the note's SCHEDULED end and later stages are entitled to move
    it: `prepare_voice_layers` shortens it for `cap_sustain_ms` and the family
    caps, and speaker stealing cuts it shorter still. Every one of those is a
    consequence of the tuning levers rather than a fact about the file, so a
    piano roll drawn from `note.end` redraws the composition every time a slider
    moves and the user cannot tell a thinned passage from lost data.

    `midi_end` is the parsed note-off and nothing downstream writes to it. It is
    set here, at the one moment it is known to be untouched.

    Set as an attribute rather than a `Note` field on purpose: field order in
    that dataclass is load-bearing for the exported bytes, and this value is
    never exported.
    """
    note.midi_end = note.end
    return note


def channel_is_percussion(mid, drum_map=None) -> bool:
    """Guess whether the percussion channel really carries a kit.

    Some files put a melodic part on the percussion channel, and some put a
    real kit elsewhere. The heuristic: a genuine kit uses few distinct keys
    and most of them are keys we recognise.
    """
    # Resolved at call time, not bound as a default: the default would freeze
    # the shipped table at import, and a user who mapped the exotic keys their
    # own kit uses would still be told their kit is not one.
    drum_map = drum_table() if drum_map is None else drum_map
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
    part_percussion=None,
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
    part_percussion = part_percussion or {}
    solos_in_force = _switch_is_used(channel_solos)
    # Once, not once per note. This opens the user's percussion table, and the
    # inner loop below runs for every note_on in the file.
    drum_defaults = drum_table()
    event_looping_cache = {}
    low_cut, low_family = low_split or (0, None)
    sound_categories = palette.sound_categories()

    # clip=True clamps out-of-range data bytes rather than refusing the file.
    mid = mido.MidiFile(str(mid_path), clip=True)
    index = note_index if note_index is not None else palette.build_note_index()
    drums_on = (
        channel_is_percussion(mid, drum_defaults) if drums == "auto" else bool(drums)
    )

    # Program change is a channel message, so ONE slot per channel means the
    # last track to announce an instrument owns the channel for the rest of
    # the song. With three tracks on channel 0 that made every note after the
    # first take the bass part's program -- the window said "Violin" from its
    # own per-part reading while the compiler played a pulse wave. Track a
    # part's own program, and fall back to the channel only when its track
    # never named one.
    program_by_part = {}
    program_by_channel = {}
    active = defaultdict(list)  # (channel, pitch) -> [pending starts]
    notes: list[Note] = []
    dropped = 0
    occurrences = defaultdict(int)
    elapsed = 0.0

    for track_index, msg, elapsed in messages_with_tracks(mid):
        now = int(elapsed * 1000)
        if msg.type == "program_change":
            program_by_channel[msg.channel] = msg.program
            program_by_part[(track_index, msg.channel)] = msg.program
        elif msg.type == "note_on" and msg.velocity > 0:
            occurrence_key = (msg.channel, msg.note)
            occurrences[occurrence_key] += 1
            note_id = "%d:%d:%d" % (
                msg.channel,
                msg.note,
                occurrences[occurrence_key],
            )
            muted = in_part(channel_mutes, track_index, msg.channel)
            solo_excluded = solos_in_force and not in_part(channel_solos, track_index, msg.channel)
            audible = not muted and not solo_excluded
            if not audible and not include_silent:
                continue
            override = note_overrides.get(note_id, {})
            pitch_offset = int(override.get("pitch_offset", 0))
            note_volume_db = int(override["volume_db"]) if "volume_db" in override else None
            volume_trim_db = int(override.get("volume_trim_db", 0))
            exact_sound = for_part(channel_sounds, track_index, msg.channel)
            chosen_family = for_part(channel_families, track_index, msg.channel)
            applied_root = None
            profile_root = None
            root_confidence = None
            root_source = None
            pitch_follow = False
            if exact_sound is not None:
                shader = exact_sound
                family = sound_categories.get(shader, "exact")
                profile = for_part(channel_pitch_profiles, track_index, msg.channel, {})
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
            elif is_percussion_part(part_percussion, track_index, msg.channel, drums_on):
                # The per-key choice is the user's and is final. `drum_overrides`
                # is keyed by resolved shader and exists to retimbre what the
                # TABLE picked, so applying it after a per-key override would
                # silently replace the sound someone had just chosen.
                shader = drum_key_overrides.get(msg.note)
                if shader is None:
                    shader = drum_defaults.get(msg.note)
                    if shader:
                        shader = drum_overrides.get(shader, shader)
                sustained, family = False, "drums"
            else:
                family = gm_to_family(
                    program_by_part.get(
                        (track_index, msg.channel),
                        program_by_channel.get(msg.channel, 0),
                    )
                )
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
                    # Which SMF track wrote this note. Deliberately NOT part of
                    # `id`: the occurrence counter is already per (channel,
                    # pitch) across the whole file, so ids stay unique without
                    # it -- and adding it would invalidate every `note_overrides`
                    # entry in every settings sidecar already on disk.
                    "track": track_index,
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
                notes.append(_record(annotate(note, expression, **metadata)))

    end = int(elapsed * 1000)
    for (channel, pitch), pending in active.items():
        for started, shader, sustained, family, expression, metadata in pending:
            # Still sounding when the file ended; hold it rather than drop it.
            note = Note(started, end, shader, sustained, channel, family)
            notes.append(_record(annotate(note, expression, **metadata)))

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
