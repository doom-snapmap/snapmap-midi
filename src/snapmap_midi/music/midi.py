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
    channel_sounds=None,
    event_is_looping=None,
):
    """Parse a MIDI file into paired notes plus a statistics summary.

    Family selection runs in increasing order of specificity: the program's
    default family, then a family-wide override, then a per-channel override,
    then a pitch split that sends the low register somewhere else. The last
    one to apply wins.

    `channel_mutes` silences whole channels. A muted note is skipped before
    anything else is decided about it and is NOT counted in `dropped`:
    `dropped` means the palette had no sound for a note, which is a problem
    worth reporting, and a muted note was asked for. Folding the two together
    would make the one number that says something is wrong fire every time
    somebody used a mute.

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
    no_sustain = set(decaying_families or ())
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
    elapsed = 0.0

    for msg in mid:
        elapsed += msg.time
        now = int(elapsed * 1000)
        if msg.type == "program_change":
            program[msg.channel] = msg.program
        elif msg.type == "note_on" and msg.velocity > 0:
            if msg.channel in channel_mutes:
                continue
            exact_sound = channel_sounds.get(msg.channel)
            chosen_family = channel_families.get(msg.channel)
            if exact_sound is not None:
                shader = exact_sound
                family = sound_categories.get(shader, "exact")
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
                active[(msg.channel, msg.note)].append((now, shader, sustained, family))
            else:
                dropped += 1
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            pending = active.get((msg.channel, msg.note))
            if pending:
                started, shader, sustained, family = pending.pop(0)
                note = Note(started, now, shader, sustained, msg.channel, family)
                # Note's declared field order is a byte-level compatibility
                # contract. Dataclasses without slots may still carry this UI
                # annotation without changing that ordered schema.
                note.pitch = msg.note
                notes.append(note)

    end = int(elapsed * 1000)
    for (channel, pitch), pending in active.items():
        for started, shader, sustained, family in pending:
            # Still sounding when the file ended; hold it rather than drop it.
            note = Note(started, end, shader, sustained, channel, family)
            note.pitch = pitch
            notes.append(note)

    stats = {"drums_on": drums_on, "dropped": dropped, "duration_s": round(elapsed, 2)}
    return notes, stats
