"""What a MIDI file contains, named in the user's terms rather than the compiler's.

`parse_notes` cannot answer this. By the time it returns, a program number has
become a family and the channel's own identity -- which instrument the composer
asked for -- is gone. Choosing an instrument per channel needs the question
asked before that collapse, so this reads the file separately.

It keeps the per-note histogram rather than only the extremes. The extremes
alone cannot answer the question the window exists to answer -- how many notes a
chosen family cannot reach -- and they draw the same bar for two notes as for
two thousand, so one stray low note makes a piano part look like it spans the
keyboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from snapmap_midi.music.gm import (
    DRUM_CHANNEL,
    DRUM_MAP,
    gm_drum_kit_name,
    gm_program_name,
    gm_to_family,
)
from snapmap_midi.music.midi import channel_is_percussion, messages_with_tracks


@dataclass
class ChannelInfo:
    """One channel, described the way the window's row for it has to describe it.

    `pitches` is the whole histogram rather than a summary because it is what
    every later answer is computed from: the out-of-range count, the density
    strip, and the drum-key list. Revision 1 built exactly this table inside
    `analyze` and kept only `lowest` and `highest`, which left the design's
    headline number uncomputable and drew a part's two hundred middle-C notes
    and its one stray bottom A as the same undifferentiated bar.

    `drum_keys` is empty unless `is_drums`, and a `None` value means the key is
    one `DRUM_MAP` has no sound for -- the case a channel assignment or an
    advanced per-key sidecar override can fill.
    """

    channel: int
    program: int
    program_name: str
    notes: int
    lowest: Optional[int]
    highest: Optional[int]
    is_drums: bool
    auto_family: Optional[str]
    pitches: dict
    drum_keys: dict
    track: int = 0
    track_name: str = ""

    @property
    def key(self) -> str:
        """This part's identity: the track that wrote it and the channel it uses.

        A bare channel number is not an identity. Two tracks sharing channel 0 --
        a lead and a pad, which is ordinary in a type 1 file -- are two parts a
        composer chose separately, and keying anything by channel alone merges
        them into one row that can hold only one instrument.

        The track comes first so parts sort in the order the file lists them,
        which is the order the composer sees in their editor.
        """
        return "%d:%d" % (self.track, self.channel)


@dataclass
class MidiAnalysis:
    """A whole file, plus the one judgement that had to be made while reading it.

    `drums_detected` is recorded rather than recomputed on demand because the
    heuristic behind it walks the entire file, and because the window shows it
    as the position of a switch. A switch whose position is derived twice can
    disagree with itself between the row that draws it and the compile that
    obeys it.
    """

    path: str
    duration_s: float
    drums_detected: bool
    channels: list


def analyze(mid_path, drums="auto") -> MidiAnalysis:
    """Read a file's channels without collapsing them into families.

    Takes the drums mode because the window's drums switch decides whether
    channel 9 is a kit. An analysis cached from `"auto"` would keep offering a
    family dropdown for a channel the compiler had since started routing
    through `DRUM_MAP`, so the row would describe an instrument nothing plays.

    The mode is resolved to match `parse_notes`, and that sameness is the
    point: if these two ever disagree, the window describes one arrangement
    while the compiler writes another.

    The settings document spells the mode `"auto"`, `"on"` or `"off"`, while
    `parse_notes` takes `"auto"` or a bool. Both spellings are accepted here
    because a bare `bool("off")` is True -- the string that means "no drums"
    would have forced them on, and the row for a silenced kit would have gone on
    listing the keys it was playing.
    """
    import mido

    mid = mido.MidiFile(str(mid_path), clip=True)
    if drums == "auto":
        drums_on = channel_is_percussion(mid)
    elif isinstance(drums, str):
        drums_on = drums == "on"
    else:
        drums_on = bool(drums)

    # SMF FF 03: "If in a format 0 track, or the first track in a format 1
    # file, the name of the sequence. Otherwise, the name of the track." So the
    # one name a format 0 file carries is the SONG's title, and using it as a
    # part label would print the song's name over every row. Format 1's first
    # track is the conductor and holds the sequence name for the same reason;
    # it has no notes, so it never becomes a part, but the rule is spelled out
    # here rather than left to that coincidence.
    names = {}
    for index, track in enumerate(mid.tracks):
        if mid.type == 0 or index == 0:
            names[index] = ""
            continue
        named = next((m.name for m in track if m.type == "track_name"), "")
        names[index] = named.strip()

    # Program changes are channel messages, so a later one anywhere in the file
    # is the channel's current voice. But a type 1 file normally has each track
    # announce its own instrument, and reading a neighbouring track's program
    # would rename a part the composer never touched. Prefer what the part's own
    # track said; fall back to the channel only when it said nothing.
    by_part, by_channel, seen, elapsed = {}, {}, {}, 0.0
    for track_index, msg, elapsed in messages_with_tracks(mid):
        if msg.type == "program_change":
            by_channel[msg.channel] = msg.program
            by_part[(track_index, msg.channel)] = msg.program
        elif msg.type == "note_on" and msg.velocity > 0:
            part = (track_index, msg.channel)
            entry = seen.setdefault(
                part,
                {
                    "program": by_part.get(part, by_channel.get(msg.channel, 0)),
                    "pitches": {},
                },
            )
            entry["pitches"][msg.note] = entry["pitches"].get(msg.note, 0) + 1

    channels = []
    for track_index, channel in sorted(seen):
        entry = seen[(track_index, channel)]
        pitches = entry["pitches"]
        is_drums = channel == DRUM_CHANNEL and drums_on
        channels.append(
            ChannelInfo(
                channel=channel,
                program=entry["program"],
                # On the percussion channel the program selects a kit, not an
                # instrument, so the melodic name is simply the wrong table.
                program_name=(
                    gm_drum_kit_name(entry["program"])
                    if is_drums
                    else gm_program_name(entry["program"])
                ),
                notes=sum(pitches.values()),
                lowest=min(pitches),
                highest=max(pitches),
                is_drums=is_drums,
                auto_family=None if is_drums else gm_to_family(entry["program"]),
                pitches=pitches,
                drum_keys={k: DRUM_MAP.get(k) for k in sorted(pitches)} if is_drums else {},
                track=track_index,
                track_name=names.get(track_index, ""),
            )
        )
    return MidiAnalysis(str(mid_path), round(elapsed, 2), drums_on, channels)


def as_dict(analysis: MidiAnalysis) -> dict:
    """The analysis as JSON, for the one consumer that cannot take it any other way.

    `pitches` and `drum_keys` come back with string keys because JSON has no
    integer ones. Converted here rather than left to whatever unpacks the
    payload, because the failure is silent in both directions: a reader that
    assumes integers looks up note 60, finds nothing, and draws an empty ruler
    without ever raising.
    """
    return {
        "path": analysis.path,
        "duration_s": analysis.duration_s,
        "drums_detected": analysis.drums_detected,
        "channels": [
            {
                "key": c.key,
                "track": c.track,
                "track_name": c.track_name,
                "channel": c.channel,
                "program": c.program,
                "program_name": c.program_name,
                "notes": c.notes,
                "lowest": c.lowest,
                "highest": c.highest,
                "is_drums": c.is_drums,
                "auto_family": c.auto_family,
                "pitches": {str(note): count for note, count in c.pitches.items()},
                "drum_keys": {str(key): shader for key, shader in c.drum_keys.items()},
            }
            for c in analysis.channels
        ],
    }


def notes_outside(channel: ChannelInfo, span) -> int:
    """How many of a channel's notes a family cannot reach.

    `decl_for` never fails outside the range -- it prefers the same pitch class
    an octave away, and falls back to the nearest available pitch when the class
    is absent entirely. So this is not a count of dropped notes; it is a count
    of notes that will not be the note that was written. That distinction is
    why the warning says "move to another octave" rather than "are lost".
    """
    if span is None:
        return 0
    low, high = span
    return sum(n for note, n in channel.pitches.items() if note < low or note > high)


def ruler_segments(channel: ChannelInfo, span, axis) -> Optional[dict]:
    """Where to draw a channel's notes and its instrument's reach, in percent.

    In Python rather than Javascript because every failure this geometry can
    have -- an axis that clips the family it was built to showcase, a disjoint
    range drawn as a matter of degree, a drum channel plotted on a pitch axis --
    is a failure a test can catch here and nothing can catch there.

    Returns None for the percussion channel: its lowest and highest are key
    numbers, and drawing them on a pitch axis asserts something false.
    """
    if channel.is_drums or not channel.pitches:
        return None
    floor, ceiling = axis
    reach = float(ceiling - floor)
    heaviest = max(channel.pitches.values())

    def place(note):
        return max(0.0, min(100.0, (note - floor) / reach * 100.0))

    cells = [
        {"note": note, "left": place(note), "weight": count / heaviest}
        for note, count in sorted(channel.pitches.items())
    ]
    instrument = None
    disjoint = False
    if span is not None:
        low, high = span
        left = place(low)
        instrument = {"left": left, "width": max(0.0, place(high) - left)}
        disjoint = channel.highest < low or channel.lowest > high
    return {
        "cells": cells,
        "instrument": instrument,
        "disjoint": disjoint,
        "outside": notes_outside(channel, span),
        "cell_width": 100.0 / reach,
    }
