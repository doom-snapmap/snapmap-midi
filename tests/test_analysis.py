"""Reading a MIDI file as channels, and placing those channels on a ruler.

The compiler answers "what should this play". This module answers "what is in
here", which is a different question and has to be asked before the first one
collapses a program number into a family. These tests are about the answers
being usable: names a person recognises, counts rather than extremes, and
geometry that a browser only has to position.

The geometry lives in Python precisely so it can be tested. An axis that clips
the one family the automatic mapping can never choose, a disjoint range drawn
as a slightly worse version of overhang, a drum channel plotted on a pitch axis
-- every one of those is caught here and by nothing in a stylesheet.
"""

from __future__ import annotations

import json

import pytest

from snapmap_midi.music import analysis
from snapmap_midi.music.gm import gm_drum_name, gm_program_name


def _write_midi(tmp_path, events, name="analysis.mid"):
    """Write a MIDI file from `(channel, program, note)` triples.

    `program` is `None` for "send no program change", which is the case worth
    covering on its own: a file that never names an instrument is not a file
    with no instrument, it is a file playing General MIDI program 0.
    """
    import mido

    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    for channel, program, note in events:
        if program is not None:
            track.append(mido.Message("program_change", channel=channel, program=program, time=0))
        track.append(mido.Message("note_on", channel=channel, note=note, velocity=64, time=0))
        track.append(mido.Message("note_off", channel=channel, note=note, velocity=0, time=120))
    path = tmp_path / name
    mid.save(str(path))
    return path


def _drum_kit(tmp_path, extra=()):
    """A channel-9 part the percussion heuristic will accept as a kit."""
    events = [(9, None, key) for key in (36, 38, 42) for _ in range(4)]
    events.extend((9, None, key) for key in extra)
    return _write_midi(tmp_path, events, name="kit.mid")


# ---- General MIDI names ----


@pytest.mark.parametrize(
    "program,name",
    [
        (0, "Acoustic Grand Piano"),
        (24, "Acoustic Guitar (nylon)"),
        (32, "Acoustic Bass"),
        (40, "Violin"),
        (56, "Trumpet"),
        (73, "Flute"),
        (80, "Lead 1 (square)"),
        (127, "Gunshot"),
    ],
)
def test_the_program_table_is_the_published_one(program, name):
    """These are spot checks on a shipped specification table, not on code.
    They are the boundaries of the eight-program families plus both ends, so a
    table written or regenerated one entry short shifts a name into this list
    rather than going unnoticed until a user reads "Tuba" over a flute part.
    """
    assert gm_program_name(program) == name


def test_the_program_table_holds_exactly_the_specified_names_and_no_duplicates():
    """A table transcribed one entry short still answers every lookup, just
    with the wrong name from that point on -- and a duplicate is how a dropped
    entry gets padded back to length. Both are silent; both shift the spot
    checks above, so the two tests together are what pins the table."""
    names = [gm_program_name(p) for p in range(128)]
    assert len(set(names)) == 128


def test_a_program_number_that_cannot_exist_raises():
    """Clamping would answer "Gunshot" for a program nobody has, which reads as
    a real instrument choice and hides the caller's bug behind it."""
    with pytest.raises(IndexError):
        gm_program_name(128)
    with pytest.raises(IndexError):
        gm_program_name(-1)


def test_the_percussion_table_names_the_keys_a_kit_uses():
    assert gm_drum_name(36) == "Bass Drum 1"
    assert gm_drum_name(38) == "Acoustic Snare"
    assert gm_drum_name(35) == "Acoustic Bass Drum"
    assert gm_drum_name(81) == "Open Triangle"


def test_an_unnamed_key_reads_back_as_its_number():
    """Files use keys outside the standard set and `DRUM_MAP` drops them.
    Showing the number is what lets someone find that row in the picker and
    give it a sound; an empty label leaves an unmappable row unidentifiable."""
    assert gm_drum_name(3) == "Key 3"
    assert gm_drum_name(120) == "Key 120"


# ---- analysis ----


def test_every_channel_that_plays_gets_exactly_one_entry(tmp_path):
    mid = _write_midi(tmp_path, [(0, None, 60), (2, None, 62), (5, None, 64), (0, None, 61)])
    result = analysis.analyze(mid)
    assert [c.channel for c in result.channels] == [0, 2, 5]
    assert result.path == str(mid)
    assert result.duration_s > 0


def test_the_extremes_come_from_the_notes_actually_played(tmp_path):
    mid = _write_midi(tmp_path, [(0, None, 48), (0, None, 60), (0, None, 72)])
    channel = analysis.analyze(mid).channels[0]
    assert (channel.lowest, channel.highest) == (48, 72)
    assert channel.notes == 3


def test_pitches_carry_a_count_per_note_not_just_a_span(tmp_path):
    """The count is the data the rest of the feature is built on: the ruler's
    density, and the out-of-range number the design promised. Revision 1 built
    this histogram inside `analyze` and threw it away at the door."""
    mid = _write_midi(tmp_path, [(0, None, 60)] * 3 + [(0, None, 64)])
    channel = analysis.analyze(mid).channels[0]
    assert channel.pitches == {60: 3, 64: 1}
    assert channel.notes == sum(channel.pitches.values())


def test_the_program_and_the_family_it_maps_to_are_both_reported(tmp_path):
    """The program is what the composer asked for and the family is what this
    tool can play. Showing only the second leaves a user guessing which of the
    palette's instruments a row was ever meant to be."""
    mid = _write_midi(tmp_path, [(0, 40, 60)])
    channel = analysis.analyze(mid).channels[0]
    assert (channel.program, channel.program_name) == (40, "Violin")
    assert channel.auto_family == "ins_violin"


def test_a_channel_that_never_names_an_instrument_is_program_zero(tmp_path):
    """MIDI's default, not a missing value. Reporting it as unknown would put
    an empty instrument name on a channel that plays a grand piano."""
    mid = _write_midi(tmp_path, [(0, None, 60)])
    channel = analysis.analyze(mid).channels[0]
    assert channel.program == 0
    assert channel.program_name == "Acoustic Grand Piano"
    assert channel.auto_family == "ins_piano"


def test_the_drum_channel_lists_the_keys_it_uses_and_marks_the_unmapped_ones(tmp_path):
    """A key with no sound is the row the Drums tab exists for. Omitting it
    would hide the only notes in the file that currently play nothing."""
    mid = _drum_kit(tmp_path, extra=(3,))
    channel = [c for c in analysis.analyze(mid).channels if c.is_drums][0]
    assert set(channel.drum_keys) == {3, 36, 38, 42}
    assert channel.drum_keys[3] is None
    assert channel.drum_keys[36]
    assert channel.auto_family is None


def test_a_melodic_part_on_the_percussion_channel_is_not_a_kit(tmp_path):
    """Channel 9 is a convention, not a guarantee. Routing a bass line through
    `DRUM_MAP` turns it into rimshots and drops most of it."""
    mid = _write_midi(tmp_path, [(9, None, note) for note in range(48, 76)], name="melodic9.mid")
    result = analysis.analyze(mid)
    assert result.drums_detected is False
    assert result.channels[0].is_drums is False
    assert result.channels[0].drum_keys == {}


def test_the_drums_switch_overrides_the_heuristic(tmp_path):
    """The heuristic is a guess and the window shows it as a switch. If the
    analysis ignored the switch, the row would offer a family dropdown for a
    channel the compiler had already started routing through `DRUM_MAP`."""
    mid = _write_midi(tmp_path, [(9, None, note) for note in range(48, 76)], name="melodic9.mid")
    forced = analysis.analyze(mid, drums="on")
    assert forced.drums_detected is True
    assert forced.channels[0].is_drums is True
    assert forced.channels[0].auto_family is None


def _multitrack(tmp_path, parts, name="multitrack.mid"):
    """A type 1 file, one track per `(name, channel, program, [notes])` part."""
    import mido

    mid = mido.MidiFile(type=1)
    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
    conductor.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(conductor)
    for label, channel, program, notes in parts:
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=label, time=0))
        if program is not None:
            track.append(mido.Message("program_change", channel=channel, program=program, time=0))
        for note in notes:
            track.append(mido.Message("note_on", channel=channel, note=note, velocity=100, time=0))
            track.append(mido.Message("note_off", channel=channel, note=note, velocity=0, time=240))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)
    path = tmp_path / name
    mid.save(str(path))
    return path


def test_two_tracks_sharing_one_channel_are_two_parts(tmp_path):
    """The headline: a channel number is not a part identity.

    A type 1 file routinely writes several parts to channel 0. Keying the
    analysis by channel merged them into one row that could hold only one
    instrument, so choosing a sound for the lead silently retimbred the pad.
    """
    mid = _multitrack(
        tmp_path,
        [
            ("lead", 0, 40, [72, 74, 76]),
            ("pad", 0, 48, [48, 50]),
        ],
    )

    result = analysis.analyze(mid)

    assert [c.key for c in result.channels] == ["1:0", "2:0"]
    assert [c.track_name for c in result.channels] == ["lead", "pad"]
    assert [c.notes for c in result.channels] == [3, 2]
    assert [c.channel for c in result.channels] == [0, 0]


def test_each_part_keeps_the_instrument_its_own_track_named(tmp_path):
    """Program change is a channel message, so the last one anywhere in the file
    is the channel's voice. Reading a neighbour's program would rename a part
    nobody touched."""
    mid = _multitrack(
        tmp_path,
        [
            ("violin", 0, 40, [72]),
            ("strings", 0, 48, [48]),
        ],
    )

    result = analysis.analyze(mid)

    assert [c.program for c in result.channels] == [40, 48]
    assert [c.program_name for c in result.channels] == [
        gm_program_name(40),
        gm_program_name(48),
    ]


def test_one_track_on_several_channels_is_still_one_part_per_channel(tmp_path):
    """The type 0 shape, and the byte-gate fixture's shape. Track 0 carrying
    three channels stays three parts, exactly as before tracks existed here."""
    mid = _write_midi(tmp_path, [(0, 40, 60), (1, 48, 62), (5, 0, 64)], name="one-track.mid")

    result = analysis.analyze(mid)

    assert [c.key for c in result.channels] == ["0:0", "0:1", "0:5"]
    assert [c.track for c in result.channels] == [0, 0, 0]


def test_as_dict_survives_the_trip_through_json(tmp_path):
    """Everything here crosses into Javascript, where an integer dict key does
    not exist. Converting on the way out is what keeps the window from
    indexing `pitches[60]`, finding nothing, and drawing an empty ruler."""
    mid = _drum_kit(tmp_path, extra=(3,))
    mid2 = _write_midi(tmp_path, [(0, 40, 60)] * 2, name="melody.mid")
    for path in (mid, mid2):
        payload = json.loads(json.dumps(analysis.as_dict(analysis.analyze(path))))
        assert set(payload) == {"path", "duration_s", "drums_detected", "channels"}
        for channel in payload["channels"]:
            assert set(channel) == {
                "key",
                "track",
                "track_name",
                "channel",
                "program",
                "program_name",
                "notes",
                "lowest",
                "highest",
                "is_drums",
                "auto_family",
                "pitches",
                "drum_keys",
            }
            assert all(isinstance(k, str) for k in channel["pitches"])
            assert all(isinstance(k, str) for k in channel["drum_keys"])
    payload = json.loads(json.dumps(analysis.as_dict(analysis.analyze(mid2))))
    assert payload["channels"][0]["pitches"] == {"60": 2}


# ---- geometry ----


def test_notes_outside_counts_what_the_range_cannot_reach(tmp_path):
    """The number the design promised and revision 1 never computed. `analyze`
    was already building this histogram and discarding it."""
    mid = _write_midi(tmp_path, [(0, None, 30), (0, None, 40), (0, None, 100)])
    channel = analysis.analyze(mid).channels[0]
    assert analysis.notes_outside(channel, (36, 67)) == 2
    assert analysis.notes_outside(channel, None) == 0


def test_notes_outside_counts_notes_and_not_distinct_pitches(tmp_path):
    """Fifty low notes are fifty transpositions a listener hears fifty times.
    Counting the histogram's keys would report one."""
    mid = _write_midi(tmp_path, [(0, None, 24)] * 5 + [(0, None, 60)])
    channel = analysis.analyze(mid).channels[0]
    assert analysis.notes_outside(channel, (36, 67)) == 5


def test_ruler_segments_place_the_bars_as_percentages(tmp_path):
    mid = _write_midi(tmp_path, [(0, None, 60)])
    channel = analysis.analyze(mid).channels[0]
    seg = analysis.ruler_segments(channel, (36, 67), (0, 127))
    assert seg["instrument"]["left"] == pytest.approx(36 / 127 * 100)
    assert seg["cells"][0]["left"] == pytest.approx(60 / 127 * 100)
    assert seg["disjoint"] is False


def test_a_family_that_shares_no_note_with_the_channel_is_marked_disjoint(tmp_path):
    """Zero overlap is not "slightly worse" -- every note is transposed and the
    melody is gone. Revision 1 drew it as a more saturated version of ordinary
    overhang, which reads as a matter of degree."""
    mid = _write_midi(tmp_path, [(0, None, 25), (0, None, 30)])
    channel = analysis.analyze(mid).channels[0]
    assert analysis.ruler_segments(channel, (36, 67), (0, 127))["disjoint"] is True


def test_a_range_that_merely_overhangs_is_not_disjoint(tmp_path):
    """The other half. A family that reaches most of a part must not be
    reported in the same words as one that reaches none of it."""
    mid = _write_midi(tmp_path, [(0, None, 30), (0, None, 60)])
    channel = analysis.analyze(mid).channels[0]
    seg = analysis.ruler_segments(channel, (36, 67), (0, 127))
    assert seg["disjoint"] is False
    assert seg["outside"] == 1


def test_a_note_above_the_old_axis_is_not_clipped(tmp_path):
    """`ins_brass_bells` reaches 112. Revision 1's axis stopped at 108 with
    overflow hidden, so the one family the automatic mapping can never choose
    -- the whole argument for having a picker -- rendered as if it stopped at
    C8."""
    mid = _write_midi(tmp_path, [(0, None, 112)])
    channel = analysis.analyze(mid).channels[0]
    seg = analysis.ruler_segments(channel, (72, 112), (0, 127))
    assert seg["instrument"]["left"] + seg["instrument"]["width"] <= 100.0
    assert all(c["left"] <= 100.0 for c in seg["cells"])


def test_a_range_that_runs_past_the_axis_is_clamped_rather_than_dropped(tmp_path):
    """A family whose reach exceeds the axis must still draw a track. Letting
    the percentage past 100 puts the hatching outside the row, which looks
    identical to a family with no range at all."""
    mid = _write_midi(tmp_path, [(0, None, 60)])
    channel = analysis.analyze(mid).channels[0]
    seg = analysis.ruler_segments(channel, (-12, 200), (0, 127))
    assert seg["instrument"]["left"] == 0.0
    assert seg["instrument"]["left"] + seg["instrument"]["width"] == pytest.approx(100.0)


def test_the_drum_channel_has_no_ruler(tmp_path):
    """Its lowest and highest are KEY numbers 35-81. Plotting them on a pitch
    axis asserts something false about what the channel plays."""
    mid = _write_midi(tmp_path, [(9, None, 36), (9, None, 38)])
    channel = [c for c in analysis.analyze(mid).channels if c.is_drums][0]
    assert analysis.ruler_segments(channel, None, (0, 127)) is None


def test_density_survives_an_outlier(tmp_path):
    """A min/max span bar draws the same rectangle for two notes and two
    thousand, so one stray low note makes a piano part look like it spans the
    keyboard. Cells carry weight."""
    mid = _write_midi(tmp_path, [(0, None, 60)] * 50 + [(0, None, 21)])
    seg = analysis.ruler_segments(analysis.analyze(mid).channels[0], None, (0, 127))
    heavy = max(seg["cells"], key=lambda c: c["weight"])
    assert heavy["note"] == 60
    assert min(c["weight"] for c in seg["cells"]) < heavy["weight"]


def test_a_ruler_with_no_family_chosen_still_draws_the_notes(tmp_path):
    """Before anything is picked the row still has to show what the channel
    plays, or the file reads as empty until a dropdown is touched."""
    mid = _write_midi(tmp_path, [(0, None, 60)])
    seg = analysis.ruler_segments(analysis.analyze(mid).channels[0], None, (0, 127))
    assert seg["instrument"] is None
    assert seg["disjoint"] is False
    assert seg["outside"] == 0
    assert seg["cells"] and seg["cell_width"] == pytest.approx(100.0 / 127)
