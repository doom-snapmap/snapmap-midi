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

from snapmap_midi import palette
from snapmap_midi.gm import DRUM_CHANNEL, DRUM_MAP, SUSTAINED, gm_to_family


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


def parse_notes(
    mid_path,
    drums="auto",
    family_overrides=None,
    decaying_families=None,
    channel_families=None,
    low_split=None,
    drum_overrides=None,
    note_index=None,
):
    """Parse a MIDI file into paired notes plus a statistics summary.

    Family selection runs in increasing order of specificity: the program's
    default family, then a family-wide override, then a per-channel override,
    then a pitch split that sends the low register somewhere else. The last
    one to apply wins.
    """
    import mido

    family_overrides = family_overrides or {}
    drum_overrides = drum_overrides or {}
    channel_families = channel_families or {}
    no_sustain = set(decaying_families or ())
    low_cut, low_family = low_split or (0, None)

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
            if msg.channel == DRUM_CHANNEL and drums_on:
                shader, sustained, family = DRUM_MAP.get(msg.note), False, "drums"
                if shader:
                    shader = drum_overrides.get(shader, shader)
            else:
                family = gm_to_family(program.get(msg.channel, 0))
                family = family_overrides.get(family, family)
                if msg.channel in channel_families:
                    family = channel_families[msg.channel]
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
                notes.append(Note(started, now, shader, sustained, msg.channel, family))

    end = int(elapsed * 1000)
    for (channel, _pitch), pending in active.items():
        for started, shader, sustained, family in pending:
            # Still sounding when the file ended; hold it rather than drop it.
            notes.append(Note(started, end, shader, sustained, channel, family))

    stats = {"drums_on": drums_on, "dropped": dropped, "duration_s": round(elapsed, 2)}
    return notes, stats
