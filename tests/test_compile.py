"""The MIDI compiler: mapping, pairing, voice allocation, and the byte gates.

Everything here is hermetic, including the headline gate, because a compile
now needs nothing but a MIDI file. The few tests that compile AGAINST a saved
map carry the `savedmap` marker and skip when none is configured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import mido
import pytest

from snapmap_midi import paths
from snapmap_midi.compile import compile_to_rawmap
from snapmap_midi.music.gm import DRUM_MAP, SUSTAINED, gm_to_family
from snapmap_midi.music.midi import Note, parse_notes
from snapmap_midi.rawmap import template
from snapmap_midi.rawmap.codec import deserialize
from snapmap_midi.sound.events import (
    START_CHANNEL,
    STOP_CHANNEL,
    events_block,
    fade,
    fade_pitch,
    start,
    stop,
)
from snapmap_midi.sound.palette import (
    build_note_index,
    decl_for,
    load_palette,
    shader_pitch,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_MIDI = FIXTURES / "tiny.mid"
GOLDEN = FIXTURES / "tiny_song_default.json"

# Compile parameters the golden is named for. Changing any of these means a
# NEW golden under a new name, never an overwrite of this one.
_GOLDEN_PARAMS = dict(button_name="claude-test-song", drums="auto", max_speakers=32)

# A synthetic palette, so pairing and family selection can be tested without
# the real one.
_SYNTHETIC_INDEX = {
    "ins_piano": {60: "play_pianoc4", 62: "play_pianod4", 72: "play_pianoc5"},
    "ins_violin": {48: "play_violinc3", 67: "play_violing4"},
    "ins_sine": {48: "play_sinec3", 67: "play_sineg4"},
}


# ---- pure logic ----


def test_gm_to_family_band_edges():
    assert gm_to_family(0) == "ins_piano"
    assert gm_to_family(40) == "ins_violin"
    assert gm_to_family(56) == "ins_trumpet"
    assert gm_to_family(73) == "ins_flute"
    assert gm_to_family(127) == "ins_marimba"


def test_shader_pitch():
    assert shader_pitch("play_pianoc4") == 60
    assert shader_pitch("play_violindb6") == 85
    assert shader_pitch("play_noise_kick_tight") is None


def test_decl_for_prefers_same_pitch_class_over_nearest():
    """An octave displacement keeps the melody in key; the nearest absolute
    pitch would bend it out of key."""
    index = {"ins_piano": {60: "play_pianoc4", 62: "play_pianod4", 72: "play_pianoc5"}}
    assert decl_for("ins_piano", 60, index) == "play_pianoc4"
    assert decl_for("ins_piano", 84, index) == "play_pianoc5"
    assert decl_for("ins_missing", 60, index) is None


def test_eventcall_encodings_match_proven_forms():
    """Shapes established against the running game: the sound argument is a
    NESTED declaration pointer, the count key carries a leading newline, and
    channels are enum-keyed."""
    s = start("play_pianoc4", 420)
    assert s["eventCall"]["\neventHandle_t eventDef"] == "startSoundShader"
    assert s["eventCall"]["args"]["item[0]"] == {"decl": {"sound": "play_pianoc4"}}
    assert s["eventCall"]["args"]["item[1]"] == {"soundChannel_t": START_CHANNEL}
    assert s["eventCall"]["args"]["\nnum"] == 2
    assert s["eventTime"] == 420

    st = stop(1000)
    assert st["eventCall"]["\neventHandle_t eventDef"] == "stopSound"
    assert st["eventCall"]["args"]["item[0]"] == {"soundChannel_t": STOP_CHANNEL}

    f = fade(1000, to_db=-60.0, over_s=0.1)
    assert f["eventCall"]["\neventHandle_t eventDef"] == "fadeSound"
    assert f["eventCall"]["args"]["\nnum"] == 3

    pitch = fade_pitch(1000, to_semitones=-7, over_s=0)
    assert pitch["eventCall"]["\neventHandle_t eventDef"] == "fadePitch"
    assert pitch["eventCall"]["args"]["item[0]"] == {"soundChannel_t": STOP_CHANNEL}
    assert pitch["eventCall"]["args"]["item[1]"] == {"float": -7.0}
    assert pitch["eventCall"]["args"]["item[2]"] == {"float": 0.0}
    assert pitch["eventTime"] == 1000

    fractional = fade_pitch(1200, to_semitones=-0.25, over_s=0)
    assert fractional["eventCall"]["args"]["item[1]"] == {"float": -0.25}

    block = events_block([s, st])
    assert block["num"] == 2 and "item[0]" in block and "item[1]" in block
    # The count key is inserted last and key order is preserved on output.
    assert list(block)[-1] == "num"


def test_note_field_order_is_pinned():
    """Field declaration order becomes key order in anything derived from this
    record, and the format preserves key order rather than sorting. Reordering
    these changes output bytes with no semantic change."""
    assert [f for f in Note.__dataclass_fields__] == [
        "start",
        "end",
        "shader",
        "sustained",
        "chan",
        "fam",
        "voice",
    ]


# ---- MIDI parsing (hermetic, against a synthetic palette) ----


def _drumless_midi(tmp_path):
    mid = mido.MidiFile()
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=0, time=0))
    tr.append(mido.Message("program_change", channel=1, program=40, time=0))
    tr.append(mido.Message("note_on", channel=0, note=60, velocity=64, time=0))
    tr.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=480))
    tr.append(mido.Message("note_on", channel=1, note=67, velocity=64, time=0))
    tr.append(mido.Message("note_off", channel=1, note=67, velocity=0, time=480))
    tr.append(mido.Message("note_on", channel=1, note=48, velocity=64, time=0))
    tr.append(mido.Message("note_off", channel=1, note=48, velocity=0, time=240))
    p = tmp_path / "drumless.mid"
    mid.save(str(p))
    return p


def _two_thick_chords(tmp_path):
    """Two tracks, each building a five-note chord one note at a time.

    STAGGERED on purpose, and DESCENDING on purpose. Notes that share an onset
    are the case where the two limits agree -- both keep the top of the chord --
    so a block chord cannot tell them apart. Notes that overlap without sharing
    an onset are the case that separates them, and that is most sustained
    writing. Descending because in an ascending line every note is the new
    highest and survives whatever the rule is.
    """
    mid = mido.MidiFile()
    for channel, program, top in ((0, 0, 72), (1, 40, 60)):
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message("program_change", channel=channel, program=program, time=0))
        for step in range(5):
            track.append(
                mido.Message(
                    "note_on",
                    channel=channel,
                    note=top - step * 2,
                    velocity=64,
                    time=0 if step == 0 else 120,
                )
            )
        for step in range(5):
            track.append(
                mido.Message(
                    "note_off",
                    channel=channel,
                    note=top - step * 2,
                    velocity=0,
                    time=960 if step == 0 else 0,
                )
            )
    path = tmp_path / "two-chords.mid"
    mid.save(str(path))
    return path


def test_global_voice_limit_caps_the_entire_song(tmp_path):
    """Global Voices is one budget, not the old repeated per-track ceiling."""
    song = _two_thick_chords(tmp_path)
    _, whole = compile_to_rawmap(song)
    _, whole_song = compile_to_rawmap(song, max_speakers=1)

    assert whole_song["voices"] == 1
    assert whole_song["voices"] < whole["voices"]


def test_track_voice_cap_limits_its_track_before_the_global_budget(tmp_path):
    song = _two_thick_chords(tmp_path)
    _, unrestricted = compile_to_rawmap(song, max_speakers=32)
    _, capped = compile_to_rawmap(song, max_speakers=32, part_voices={0: 1})

    assert capped["voices"] < unrestricted["voices"]
    assert capped["voices"] <= 32


def test_track_polyphony_mutes_notes_where_global_voices_would_cut_them(tmp_path):
    """The two levers are not the same and must not be made the same.

    Polyphony refuses the note: it never sounds, and the notes that do keep
    their full length. Global Voices shares speakers between tracks and takes
    the speaker that is closest to finishing, so older notes can stop early.
    The compiler's event count includes the stops and fades needed to reuse a
    speaker, so it no longer identifies the distinction by itself; retained
    source-note count and the polyphony compile's smaller timeline do.
    """
    song = _two_thick_chords(tmp_path)
    _, plain = compile_to_rawmap(song)
    _, voices = compile_to_rawmap(song, max_speakers=2)
    _, poly = compile_to_rawmap(song, part_polyphony={0: 2})

    # Global Voices still retains the imported notes; it only changes how the
    # limited speaker pool schedules them.
    assert voices["notes"] == plain["notes"]
    # Polyphony refuses notes, so their events are simply not written.
    assert poly["events"] < plain["events"]
    # The global cap is stricter: polyphony only thins its named track, while
    # the other track may still use speakers.
    assert voices["voices"] == 2
    assert poly["voices"] > voices["voices"]
    # Neither edits the song: the notes are all still there to be drawn.
    for stats in (voices, poly):
        assert stats["notes"] == plain["notes"]


def test_parse_notes_pairing_families_and_sustain():
    notes, stats = parse_notes(TINY_MIDI, note_index=_SYNTHETIC_INDEX)
    by_channel = {}
    for n in notes:
        by_channel.setdefault(n.chan, []).append(n)
    piano = by_channel[0][0]
    assert piano.fam == "ins_piano" and piano.sustained is False
    assert piano.end > piano.start
    assert all(n.fam == "ins_violin" and n.sustained for n in by_channel[1])
    assert stats["drums_on"] is True
    assert by_channel[9][0].shader == DRUM_MAP[36]
    assert by_channel[9][0].fam == "drums"

    assert [note.id for note in notes] == ["0:60:1", "1:67:1", "1:48:1", "9:36:1"]
    assert [note.velocity for note in notes] == [64, 64, 64, 100]
    assert all(note.volume_db <= 0 for note in notes)
    assert stats["volume_adjusted"] == 4


def test_parse_notes_channel_family_override_wins(tmp_path):
    p = _drumless_midi(tmp_path)
    notes, _ = parse_notes(p, channel_families={1: "ins_piano"}, note_index=_SYNTHETIC_INDEX)
    channel_1 = [n for n in notes if n.chan == 1]
    assert channel_1
    assert all(n.fam == "ins_piano" and n.sustained is False for n in channel_1)


def test_parse_notes_low_split(tmp_path):
    p = _drumless_midi(tmp_path)
    notes, _ = parse_notes(p, low_split=(60, "ins_sine"), note_index=_SYNTHETIC_INDEX)
    low = [n for n in notes if n.chan == 1 and (shader_pitch(n.shader) or 99) < 60]
    assert low and all(n.fam == "ins_sine" for n in low)
    assert "ins_sine" not in SUSTAINED
    assert all(not note.sustained for note in low)


def test_automatic_waveform_families_are_one_shots():
    assert not {"ins_sine", "ins_pulse", "ins_square", "ins_tri"} & SUSTAINED


def test_parse_notes_drum_override():
    notes, _ = parse_notes(
        TINY_MIDI, drum_overrides={DRUM_MAP[36]: "play_noise_hat"}, note_index=_SYNTHETIC_INDEX
    )
    drum = [n for n in notes if n.chan == 9][0]
    assert drum.shader == "play_noise_hat"


def test_parse_notes_preserves_fractional_root_and_track_tuning():
    notes, _ = parse_notes(
        TINY_MIDI,
        channel_sounds={0: "play_pianoc4"},
        channel_pitch_profiles={
            0: {
                "pitch_follow": True,
                "root_midi": 60.25,
                "pitch_transpose": 1,
                "fine_tune_cents": 50,
            }
        },
        note_index=_SYNTHETIC_INDEX,
    )

    first = next(note for note in notes if note.chan == 0)
    assert first.source_pitch == 60
    assert first.automatic_pitch == -0.25
    assert first.pitch_modifier == 1.25


def test_unpaired_note_is_held_to_the_end_not_dropped(tmp_path):
    mid = mido.MidiFile()
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=0, time=0))
    tr.append(mido.Message("note_on", channel=0, note=60, velocity=64, time=0))
    tr.append(mido.Message("note_on", channel=0, note=62, velocity=64, time=480))
    tr.append(mido.Message("note_off", channel=0, note=62, velocity=0, time=480))
    p = tmp_path / "unpaired.mid"
    mid.save(str(p))
    notes, _ = parse_notes(p, drums=False, note_index=_SYNTHETIC_INDEX)
    held = [n for n in notes if n.shader == "play_pianoc4"][0]
    assert held.end > held.start


# ---- hermetic byte gate ----
#


def test_retriggered_notes_keep_stable_source_ids_and_independent_expression(tmp_path):
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("program_change", channel=0, program=0, time=0))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=32, time=0))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=96, time=120))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=120))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=120))
    path = tmp_path / "retrigger.mid"
    mid.save(str(path))

    notes, _ = parse_notes(
        path,
        note_index=_SYNTHETIC_INDEX,
        note_overrides={"0:60:2": {"pitch_offset": 2, "volume_db": 4}},
    )

    assert [note.id for note in notes] == ["0:60:1", "0:60:2"]
    assert [note.velocity for note in notes] == [32, 96]
    assert notes[0].target_pitch == 60
    assert notes[1].target_pitch == 60
    assert notes[0].shader == notes[1].shader
    assert notes[1].pitch_offset == 2
    assert notes[1].pitch_modifier == 2
    assert notes[1].note_volume_db == 4
    assert notes[1].volume_db == 4


# The gates below this one need real game data and therefore SKIP after the
# product is lifted out of its host repository -- which would silently delete
# the entire behaviour-neutrality proof at exactly the moment it matters most.
# This one uses the synthetic baseline and synthetic palette, so it survives
# the move and keeps a byte gate on the compiler wherever the code lives.

HERMETIC_GOLDEN = FIXTURES / "tiny_song_named_layout_hermetic.json"

_HERMETIC_PARAMS = dict(button_name="hermetic-test", drums="auto", max_speakers=32)


def _hermetic_compile(minimal_timeline_map):
    return compile_to_rawmap(
        TINY_MIDI,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        **_HERMETIC_PARAMS,
    )


def test_hermetic_compile_golden_bytes(minimal_timeline_map):
    """Byte gate that needs no game data, so it survives extraction.

    Covers the compile path end to end: emitter creation, the start/fade
    builders, the events block, and multi-group entity events.
    """
    raw, _ = _hermetic_compile(minimal_timeline_map)
    # The checked-in text fixture has its conventional final newline; rawmap
    # serialization intentionally does not emit one.
    assert raw + b"\n" == HERMETIC_GOLDEN.read_bytes()


def test_hermetic_compile_structure(minimal_timeline_map):
    """Structural companion, so a byte diff says WHAT moved."""
    raw, stats = _hermetic_compile(minimal_timeline_map)
    obj = deserialize(raw)
    timeline = next(
        e
        for e in obj["entities"]
        if (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    emitters = [
        e
        for e in obj["entities"]
        if e is not timeline
        and (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    ]
    assert groups["num"] == stats["voices"] + 1
    assert len(emitters) == stats["voices"]
    assert not any(
        (e.get("entityDef") or {}).get("className") == "idSnapMapGameEntity_Speaker"
        for e in obj["entities"]
    )
    assert stats["notes"] == 4
    assert stats["decaying"] == 2 and stats["sustained"] == 2


def test_midi_filename_names_the_interactive_and_unknowns_follow_it(
    minimal_timeline_map,
):
    raw, _stats = compile_to_rawmap(
        TINY_MIDI,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        button_name="stale-pitch-probe-name",
    )
    obj = deserialize(raw)
    interactive = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idInteractable"
    )
    timelines = [
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    ]

    assert interactive["displayName"] == TINY_MIDI.name
    switch_position = interactive["entityDef"]["state"]["edit"]["spawnPosition"]
    timeline_positions = [
        entity["entityDef"]["state"]["edit"]["spawnPosition"] for entity in timelines
    ]
    assert timeline_positions[0] == {
        "x": switch_position["x"] + 25.0,
        "y": switch_position["y"] + 64.0,
        "z": switch_position["z"],
    }
    assert all(
        right["y"] - left["y"] == 32.0
        for left, right in zip(timeline_positions, timeline_positions[1:])
    )


def test_large_master_timeline_stays_single_while_sharding_is_disabled(
    minimal_timeline_map, monkeypatch
):
    # Deliberately tiny so the four-note hermetic song exercises the same path
    # a real near-1 MiB arrangement takes without building a giant fixture.
    budget = 2000
    monkeypatch.setattr("snapmap_midi.compile.TIMELINE_SERIALIZE_BUDGET", budget)

    raw, stats = _hermetic_compile(minimal_timeline_map)
    obj = deserialize(raw)
    listener = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idSnapMapListener_Simple"
    )
    targets = listener["entityDef"]["state"]["edit"]["targets"]

    assert stats["timeline_unsharded_bytes"] > budget
    assert stats["timeline_sharding_enabled"] is False
    assert stats["timeline_shards"] == targets["num"] == 1
    assert stats["timeline_bytes"] == stats["timeline_unsharded_bytes"]
    assert stats["timeline_bytes"] > budget


def test_parked_sharding_path_remains_executable(minimal_timeline_map, monkeypatch):
    """The parked implementation stays ready for deliberate reactivation."""
    budget = 2000
    monkeypatch.setattr("snapmap_midi.compile.TIMELINE_SERIALIZE_BUDGET", budget)
    monkeypatch.setattr("snapmap_midi.compile.ENABLE_TIMELINE_SHARDING", True)

    raw, stats = _hermetic_compile(minimal_timeline_map)
    obj = deserialize(raw)
    timelines = [
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    ]
    listener = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idSnapMapListener_Simple"
    )
    targets = listener["entityDef"]["state"]["edit"]["targets"]

    assert stats["timeline_sharding_enabled"] is True
    assert stats["timeline_shards"] == len(timelines) == targets["num"]
    assert stats["timeline_bytes"] <= budget
    assert all(
        entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]["num"]
        == 1
        for entity in timelines
    )
    event_count = sum(
        entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"][
            "item[0]"
        ]["events"]["num"]
        for entity in timelines
    )
    assert event_count == stats["events"]


def test_hermetic_hard_stop_emits_stop_not_fade(minimal_timeline_map):
    """Hard stop replaces only the release fade.

    Velocity expression legitimately emits fadeSound at note onset.
    """
    raw, _ = compile_to_rawmap(
        TINY_MIDI,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        hard_stop=True,
        button_name="hermetic-test",
    )
    text = raw.decode("utf-8")
    assert "stopSound" in text
    assert '"float":-60.0' not in text


def test_track_hard_stop_can_override_the_song_default(tmp_path, minimal_timeline_map):
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.extend(
        [
            mido.Message("program_change", channel=0, program=40, time=0),
            mido.Message("program_change", channel=1, program=40, time=0),
            mido.Message("note_on", channel=0, note=60, velocity=100, time=0),
            mido.Message("note_on", channel=1, note=67, velocity=100, time=0),
            mido.Message("note_off", channel=0, note=60, velocity=0, time=480),
            mido.Message("note_off", channel=1, note=67, velocity=0, time=0),
        ]
    )
    path = tmp_path / "track-hard-stop.mid"
    midi.save(path)
    raw, _ = compile_to_rawmap(
        path,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        hard_stop=True,
        part_hard_stop={1: False},
    )
    text = raw.decode("utf-8")

    assert "stopSound" in text
    assert '"float":-60.0' in text


def test_track_attack_mutes_the_live_sound_before_starting_its_gain_ramp(minimal_timeline_map):
    raw, stats = compile_to_rawmap(
        TINY_MIDI,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        part_attack_ms={0: 250},
    )
    obj = deserialize(raw)
    timeline = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    for group_index in range(groups["num"]):
        events = groups["item[%d]" % group_index]["events"]
        calls = [events["item[%d]" % index] for index in range(events["num"])]
        definitions = [call["eventCall"]["\neventHandle_t eventDef"] for call in calls]
        if definitions[:4] != ["fadePitch", "startSoundShader", "fadeSound", "fadeSound"]:
            continue
        assert [call["eventTime"] for call in calls[:4]] == [0, 0, 1, 2]
        assert calls[2]["eventCall"]["args"]["item[1]"] == {"float": -60.0}
        assert calls[3]["eventCall"]["args"]["item[2]"] == {"float": 0.25}
        break
    else:
        raise AssertionError("attack sequence was not emitted")

    assert stats["expressive_one_shots"] >= 1


def test_track_release_overrides_the_default_note_off_fade(
    tmp_path, minimal_timeline_map
):
    midi_path = tmp_path / "track-release.mid"
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.extend(
        [
            mido.Message("program_change", channel=0, program=40, time=0),
            mido.Message("note_on", channel=0, note=67, velocity=127, time=0),
            mido.Message("note_off", channel=0, note=67, velocity=0, time=480),
        ]
    )
    mid.save(midi_path)

    raw, _ = compile_to_rawmap(
        midi_path,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        release_s=0.1,
        part_release_s={0: 0.35},
        button_name="track-release-test",
    )
    obj = deserialize(raw)
    release_events = []
    for entity in obj["entities"]:
        if (entity.get("entityDef") or {}).get("className") != "idTarget_Timeline":
            continue
        groups = entity["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
        for group_index in range(groups["num"]):
            block = groups["item[%d]" % group_index]["events"]
            for event_index in range(block["num"]):
                event = block["item[%d]" % event_index]
                call = event["eventCall"]
                if (
                    call["\neventHandle_t eventDef"] == "fadeSound"
                    and call["args"]["item[1]"] == {"float": -60.0}
                ):
                    release_events.append(call)

    assert release_events
    assert all(call["args"]["item[2]"] == {"float": 0.35} for call in release_events)


def test_decaying_note_off_and_trailing_rest_do_not_add_stop_events(tmp_path):
    def compile_shape(final_note_ticks):
        mid = mido.MidiFile(ticks_per_beat=96)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.extend(
            [
                mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
                mido.Message("note_on", channel=0, note=72, velocity=127, time=672),
                mido.Message("note_off", channel=0, note=72, velocity=64, time=final_note_ticks),
            ]
        )
        # The interactive is deliberately named from the MIDI filename.
        # Reuse one filename so this test compares scheduling only.
        path = tmp_path / "shape.mid"
        mid.save(path)
        return compile_to_rawmap(path, note_index=_SYNTHETIC_INDEX)

    short_raw, short_stats = compile_shape(24)
    bar_raw, bar_stats = compile_shape(96)

    # One-shot piano events decay naturally in SnapMap. Neither their MIDI
    # note-off nor empty time before the bar line becomes a stop/no-op event.
    assert short_raw == bar_raw
    assert short_stats["events"] == bar_stats["events"] == 1
    assert b"stopSound" not in short_raw


def test_expression_events_precede_start_in_proven_equal_time_order(minimal_timeline_map):
    raw, stats = compile_to_rawmap(
        TINY_MIDI,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        channel_sounds={0: "play_pianoc4"},
        channel_pitch_profiles={0: {"pitch_follow": True, "root_midi": 60}},
        note_overrides={"0:60:1": {"pitch_offset": 1, "volume_db": 3}},
        master_volume_db=6,
        button_name="expression-test",
    )
    obj = deserialize(raw)
    timeline = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    matched = None
    for group_index in range(groups["num"]):
        block = groups["item[%d]" % group_index]["events"]
        events = [block["item[%d]" % index] for index in range(block["num"])]
        definitions = [event["eventCall"]["\neventHandle_t eventDef"] for event in events]
        if definitions[:3] == ["fadePitch", "fadeSound", "startSoundShader"]:
            matched = events[:3]
            break

    assert matched is not None
    assert [event["eventTime"] for event in matched] == [0, 0, 0]
    assert matched[0]["eventCall"]["args"]["item[1]"] == {"float": 1.0}
    assert matched[1]["eventCall"]["args"]["item[1]"] == {"float": 9.0}
    assert matched[2]["eventCall"]["args"]["item[0]"] == {"decl": {"sound": "play_pianoc4"}}
    assert stats["expressive_one_shots"] >= 1
    assert stats["pitch_adjusted"] == 1


def test_absolute_note_pitch_is_the_value_written_to_the_timeline(minimal_timeline_map):
    raw, stats = compile_to_rawmap(
        TINY_MIDI,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        channel_sounds={0: "play_pianoc4"},
        channel_pitch_profiles={0: {"pitch_follow": True, "root_midi": 60}},
        note_overrides={"0:60:1": {"follow_pitch_semitones": -3}},
        button_name="absolute-note-pitch-test",
    )
    obj = deserialize(raw)
    timeline = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    matched = None
    for group_index in range(groups["num"]):
        block = groups["item[%d]" % group_index]["events"]
        events = [block["item[%d]" % index] for index in range(block["num"])]
        definitions = [event["eventCall"]["\neventHandle_t eventDef"] for event in events]
        if definitions[:3] == ["fadePitch", "fadeSound", "startSoundShader"]:
            matched = events[:3]
            break

    assert matched is not None
    assert matched[0]["eventCall"]["args"]["item[1]"] == {"float": -3.0}
    assert stats["pitch_adjusted"] == 1


def test_monophonic_track_glide_ramps_from_the_previous_pitch(tmp_path, minimal_timeline_map):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.extend(
        [
            mido.Message("note_on", channel=0, note=60, velocity=100, time=0),
            mido.Message("note_off", channel=0, note=60, velocity=0, time=240),
            mido.Message("note_on", channel=0, note=62, velocity=100, time=240),
            mido.Message("note_off", channel=0, note=62, velocity=0, time=240),
        ]
    )
    path = tmp_path / "glide.mid"
    mid.save(path)

    raw, stats = compile_to_rawmap(
        path,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        channel_sounds={0: "play_pianoc4"},
        channel_pitch_profiles={0: {"pitch_follow": True, "root_midi": 60}},
        part_voices={0: 1},
        part_glide_ms={0: 250},
    )
    obj = deserialize(raw)
    timeline = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    pitches = []
    for group_index in range(groups["num"]):
        block = groups["item[%d]" % group_index]["events"]
        for event_index in range(block["num"]):
            event = block["item[%d]" % event_index]
            if event["eventCall"]["\neventHandle_t eventDef"] == "fadePitch":
                pitches.append(event)

    glide = next(event for event in pitches if event["eventTime"] == 501)
    assert glide["eventCall"]["args"]["item[1]"] == {"float": 2.0}
    assert glide["eventCall"]["args"]["item[2]"] == {"float": 0.25}
    assert stats["voices"] == 1
    assert not any(
        (entity.get("entityDef") or {}).get("className")
        == "idSnapMapGameEntity_Speaker"
        for entity in obj["entities"]
    )


def test_export_uses_the_sound_root_octave_without_silent_transposition(
    tmp_path, minimal_timeline_map
):
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("program_change", channel=0, program=0, time=0))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=127, time=0))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=120))
    path = tmp_path / "absolute-pitch.mid"
    mid.save(str(path))

    raw, _ = compile_to_rawmap(
        path,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        channel_sounds={0: "play_custom_tone"},
        channel_pitch_profiles={0: {"pitch_follow": True, "root_midi": 72}},
        button_name="absolute-pitch-test",
    )
    obj = deserialize(raw)
    timeline = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    pitch_values = []
    for group_index in range(groups["num"]):
        block = groups["item[%d]" % group_index]["events"]
        for event_index in range(block["num"]):
            event = block["item[%d]" % event_index]
            if event["eventCall"]["\neventHandle_t eventDef"] == "fadePitch":
                pitch_values.append(event["eventCall"]["args"]["item[1]"]["float"])

    assert pitch_values == [-12.0]


def test_neutral_one_shot_keeps_the_shared_timeline_fast_path(tmp_path, minimal_timeline_map):
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("program_change", channel=0, program=0, time=0))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=127, time=0))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=120))
    path = tmp_path / "neutral.mid"
    mid.save(str(path))

    raw, stats = compile_to_rawmap(
        path,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        button_name="neutral-test",
    )
    obj = deserialize(raw)
    timeline = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    shared = groups["item[0]"]["events"]

    assert stats["shared_one_shots"] == 1
    assert stats["expressive_one_shots"] == 0
    assert stats["voices"] == 0
    assert groups["num"] == 1
    assert shared["num"] == 1
    assert shared["item[0]"]["eventCall"]["\neventHandle_t eventDef"] == "startSoundShader"


def test_sustain_limited_one_shot_gets_its_own_release_event(
    tmp_path, minimal_timeline_map
):
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.extend(
        [
            mido.Message("program_change", channel=0, program=0, time=0),
            mido.Message("note_on", channel=0, note=60, velocity=127, time=0),
            mido.Message("note_off", channel=0, note=60, velocity=0, time=120),
        ]
    )
    path = tmp_path / "capped-one-shot.mid"
    mid.save(str(path))

    raw, stats = compile_to_rawmap(
        path,
        json.dumps(minimal_timeline_map).encode("utf-8"),
        note_index=_SYNTHETIC_INDEX,
        cap_sustain_ms=300,
    )
    obj = deserialize(raw)
    timeline = next(
        entity
        for entity in obj["entities"]
        if (entity.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    calls = [
        groups["item[%d]" % group_index]["events"]["item[%d]" % event_index]
        for group_index in range(groups["num"])
        for event_index in range(groups["item[%d]" % group_index]["events"]["num"])
    ]
    cap_release = next(
        event
        for event in calls
        if event["eventTime"] == 300
        and event["eventCall"]["\neventHandle_t eventDef"] == "fadeSound"
    )

    assert stats["shared_one_shots"] == 0
    assert stats["expressive_one_shots"] == 1
    assert stats["voices"] == 1
    assert cap_release["eventCall"]["args"]["item[1]"] == {"float": -60.0}


def test_hermetic_multi_voice_authors_generic_timeline_emitters(minimal_timeline_map):
    """Two overlapping sustained notes need two independent emitters, but the
    live pitch path proves those entities must be generic Timelines rather than
    SnapMap Speakers."""
    import mido

    mid = mido.MidiFile()
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=1, program=40, time=0))
    tr.append(mido.Message("note_on", channel=1, note=67, velocity=64, time=0))
    tr.append(mido.Message("note_on", channel=1, note=48, velocity=64, time=120))
    tr.append(mido.Message("note_off", channel=1, note=67, velocity=0, time=480))
    tr.append(mido.Message("note_off", channel=1, note=48, velocity=0, time=120))
    path = FIXTURES / "_tmp_overlap.mid"
    try:
        mid.save(str(path))
        raw, stats = compile_to_rawmap(
            path,
            json.dumps(minimal_timeline_map).encode("utf-8"),
            note_index=_SYNTHETIC_INDEX,
            button_name="hermetic-test",
        )
    finally:
        path.unlink(missing_ok=True)
    assert stats["voices"] == 2
    obj = deserialize(raw)
    emitters = [
        e
        for e in obj["entities"]
        if (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
        and e.get("displayName", "").startswith("snapmap-midi-v")
    ]
    assert len(emitters) == 2
    assert [e["displayName"] for e in emitters] == ["snapmap-midi-v0", "snapmap-midi-v1"]
    assert not any(
        (e.get("entityDef") or {}).get("className") == "idSnapMapGameEntity_Speaker"
        for e in obj["entities"]
    )


def test_speakers_stay_inside_the_room_however_many_there_are():
    """They used to march out from x = 120 with no bound at all, 24 units at a
    time. A song needing 112 of them put the last one at x = 2,784 -- roughly
    twice as far out as any point known to be inside this room -- and they
    landed outside the module, entities the editor has to place in a room that
    does not contain them.

    Wrapping rather than running on is safe here specifically because these are
    2D speakers: their output is not positional, so two sharing a spot costs
    nothing, while one outside the room is a real problem.
    """
    from snapmap_midi.rawmap import template

    for index in (0, 1, 50, 111, 500, 5000):
        x, y, z = template.speaker_position(index)
        assert template.INTERIOR_X_MIN <= x <= template.INTERIOR_X_MAX, (index, x)
        assert z > 0.0, index
    # Distinct while the room has room for them, so an ordinary song's speakers
    # do not all land on one spot.
    span = template.INTERIOR_X_MAX - template.INTERIOR_X_MIN
    fits = span // template.SPEAKER_SPACING
    assert len({template.speaker_position(i)[0] for i in range(fits)}) == fits


# ---- byte gates (need the real palette and baseline) ----


@pytest.mark.savedmap
def test_compile_golden_bytes():
    """Byte gate. If this moves while the structural gate still passes,
    suspect an accidental key-order change -- not an improvement."""
    raw, _ = compile_to_rawmap(TINY_MIDI, paths.baseline_map().read_bytes(), **_GOLDEN_PARAMS)
    assert raw == GOLDEN.read_bytes()


@pytest.mark.savedmap
def test_compile_golden_structure():
    """Structural gate. Tells you WHAT moved when the byte gate fails."""
    raw, stats = compile_to_rawmap(TINY_MIDI, paths.baseline_map().read_bytes(), **_GOLDEN_PARAMS)
    obj = deserialize(raw)
    timeline = next(
        e
        for e in obj["entities"]
        if (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    )
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    emitters = [
        e
        for e in obj["entities"]
        if e is not timeline
        and (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    ]
    assert groups["num"] == stats["voices"] + 1  # group 0 plus one per voice
    # Exact equality holds only because this baseline has no pre-existing
    # auxiliary timelines. Against another baseline this must become a delta.
    assert len(emitters) == stats["voices"]
    assert stats["drums_on"] is True
    assert stats["decaying"] >= 2  # piano note plus kick
    assert stats["sustained"] >= 2  # both string notes


@pytest.mark.savedmap
def test_compile_end_to_end_produces_a_timeline():
    raw, stats = compile_to_rawmap(
        TINY_MIDI, paths.baseline_map().read_bytes(), button_name="claude-test-song"
    )
    assert stats["drums_on"] is True
    obj = deserialize(raw)
    classes = [(e.get("entityDef") or {}).get("className") for e in obj["entities"]]
    assert "idTarget_Timeline" in classes


def test_shipped_palette_indexes_pitched_sounds():
    """No marker and no skip: the palette ships, so this runs everywhere.

    It used to need a configured game file, which meant the one test proving
    the palette parses at all never ran in CI or on a contributor's machine.
    """
    index = build_note_index()
    assert index, "the palette parsed to nothing"
    for family in ("ins_piano", "ins_violin", "ins_flute"):
        assert family in index, "no %s category in the shipped palette" % family
    # Middle C has to resolve, or every melody lands on a fallback.
    assert decl_for("ins_piano", 60, index) == "play_pianoc4"


def test_shipped_palette_covers_every_family_the_tables_name():
    """`gm.py` maps program numbers onto family names and `DRUM_MAP` names
    percussion sounds outright. Either naming something the palette does not
    contain compiles to silence, which looks like success."""
    palette = load_palette()
    everything = {sound for sounds in palette.values() for sound in sounds}

    families = {gm_to_family(program) for program in range(128)}
    missing = sorted(f for f in families | SUSTAINED if f not in palette)
    assert not missing, "families with no sounds in the palette: %s" % missing

    absent = sorted(s for s in set(DRUM_MAP.values()) if s not in everything)
    assert not absent, "drum sounds absent from the palette: %s" % absent


def test_compiles_with_no_inputs_at_all():
    """The headline: a MIDI file, and nothing else. No palette to configure,
    no baseline map to find."""
    raw, stats = compile_to_rawmap(TINY_MIDI, button_name="from-scratch")
    obj = deserialize(raw)
    classes = [(e.get("entityDef") or {}).get("className") for e in obj["entities"]]
    assert "idTarget_Timeline" in classes
    assert stats["notes"] > 0 and stats["dropped"] == 0


# ---- from-scratch byte gate ----
#
# The default path now authors its own map, so it needs its own gate. The
# hermetic gate below covers a compile against a supplied baseline and would
# not notice the stage itself changing: a cap losing its rotation, the player
# start moving, a reference table sized differently. All of those are silent
# in every structural assertion and fatal in game.

SCRATCH_GOLDEN = FIXTURES / "tiny_song_named_layout_scratch.json"

_SCRATCH_PARAMS = dict(button_name="scratch-test", drums="auto", max_speakers=32)


def test_from_scratch_golden_bytes():
    """Byte gate on the map authored from nothing, palette included.

    This one gate covers more than any other: the shipped palette resolving
    the same sounds, the blank stage, the synthesized timeline, and the whole
    compile on top of them.
    """
    raw, _ = compile_to_rawmap(TINY_MIDI, **_SCRATCH_PARAMS)
    assert raw + b"\n" == SCRATCH_GOLDEN.read_bytes()


def test_from_scratch_golden_structure():
    """Structural companion, so a byte diff says WHAT moved."""
    raw, stats = compile_to_rawmap(TINY_MIDI, **_SCRATCH_PARAMS)
    obj = deserialize(raw)
    by_class = {}
    for e in obj["entities"]:
        by_class.setdefault((e.get("entityDef") or {}).get("className"), []).append(e)

    # The stage: both portals capped, somewhere to spawn, one master scheduler.
    assert len(by_class["idSnapMapCapEntity"]) == 2
    assert obj["doorsAndCaps"]["portalDoors"] == [
        e["uniqueId"] for e in by_class["idSnapMapCapEntity"]
    ]
    assert len(by_class["idSnapMapGameEntity_ComboStart"]) == 1
    assert len(by_class["idTarget_Timeline"]) == stats["voices"] + 1
    # The song: one group per voice plus the shared one-shot group.
    timeline = by_class["idTarget_Timeline"][0]
    groups = timeline["entityDef"]["state"]["edit"]["componentTimeLine"]["entityEvents"]
    assert groups["num"] == stats["voices"] + 1
    assert "idSnapMapGameEntity_Speaker" not in by_class
    # The trigger: a switch wired through a listener, and nothing else wired.
    assert len(by_class["idInteractable"]) == 1
    assert len(by_class["idSnapMapListener_Simple"]) == 1
    assert obj["targets"]["connections"] == [
        -(by_class["idInteractable"][0]["uniqueId"] + 1),
        by_class["idSnapMapListener_Simple"][0]["uniqueId"],
    ]
    # Every entity registered against its instance, or the engine cannot see it.
    assert obj["instanceEntities"]["values"] == [e["uniqueId"] for e in obj["entities"]]


def test_global_voice_cap_keeps_dense_song_tables_consistent(tmp_path):
    """Even a very dense arrangement authors no more global speakers than its
    cap, while the blank stage's reference tables stay well-formed."""
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    channels = [c for c in range(16) if c != 9]  # 9 is percussion
    for channel in channels:
        track.append(mido.Message("program_change", channel=channel, program=40, time=0))
    for channel in channels:
        for n in range(40):
            track.append(mido.Message("note_on", channel=channel, note=40 + n, velocity=80, time=0))
    # Every note overlaps every other, so each one needs its own speaker.
    first = True
    for channel in channels:
        for n in range(40):
            track.append(
                mido.Message(
                    "note_off", channel=channel, note=40 + n, velocity=0, time=8000 if first else 0
                )
            )
            first = False
    path = tmp_path / "dense.mid"
    mid.save(str(path))

    raw, stats = compile_to_rawmap(
        path,
        max_speakers=64,
        song_polyphony=128,
        button_name="dense",
    )
    obj = deserialize(raw)
    uids = [e["uniqueId"] for e in obj["entities"]]
    assert max(uids) < template.REFERENCE_TABLE_WIDTH
    assert stats["voices"] == 64
    assert stats["voices"] == len([u for u in uids]) - 6  # stage(4) + switch + listener

    for table in ("entityEntRefs", "entityVarRefs"):
        keys = obj["references"][table]["keyValues"]
        values = obj["references"][table]["values"]
        assert len(keys) >= max(uids) + 2, "%s not readable one past the last id" % table
        assert all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1)), "%s not monotonic" % table
        assert keys[-1] == len(values), "%s prefix sum disagrees with its values" % table

    assert obj["instanceEntities"]["values"] == uids


def test_from_scratch_switch_is_reachable_from_the_spawn():
    """A switch the player cannot walk to is a song that never plays."""
    obj = deserialize(compile_to_rawmap(TINY_MIDI, **_SCRATCH_PARAMS)[0])

    def position(class_name):
        entity = next(
            e for e in obj["entities"] if (e.get("entityDef") or {}).get("className") == class_name
        )
        edit = entity["entityDef"]["state"]["edit"].get("spawnPosition", {})
        return (edit.get("x", 0), edit.get("y", 0), edit.get("z", 0))

    spawn = position("idSnapMapGameEntity_ComboStart")
    switch = position("idInteractable")
    distance = sum((a - b) ** 2 for a, b in zip(spawn, switch)) ** 0.5
    assert distance < 256, "switch is %.0f units from the spawn" % distance


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
