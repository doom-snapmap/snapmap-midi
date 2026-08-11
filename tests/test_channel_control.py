"""Per-channel mute, per-drum-key remap, and the statistics the engine limit justifies.

Three separate claims live here, and they fail in different ways:

  - A muted channel contributes nothing, and is not reported as a problem. A
    note the user silenced on purpose showing up in `dropped` turns the one
    number that means "the palette had no sound for this" into noise.
  - A per-key drum choice is the user's and is final. `drum_overrides` is keyed
    by resolved shader and post-processes what the TABLE picked, so applying it
    on top of a per-key override silently replaces a sound just chosen.
  - The statistics name what `docs/limits.md` names. Total event count is
    not a density measure; shared neutral one-shots and isolated expressive
    notes are reported separately from peak per-channel voice use.

The byte gate at the end is the fourth claim: both levers are inert when empty.
"""

from __future__ import annotations

from pathlib import Path

import mido
import pytest

from snapmap_midi.compile import compile_to_rawmap
from snapmap_midi.music.gm import DRUM_MAP
from snapmap_midi.music.midi import parse_notes
from snapmap_midi.sound import palette

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_MIDI = FIXTURES / "tiny.mid"
SCRATCH_GOLDEN = FIXTURES / "tiny_song_scratch.json"

# Same parameters the from-scratch golden in `test_compile.py` is recorded
# under. Named here rather than imported so this file states what it compares.
_SCRATCH_PARAMS = dict(button_name="scratch-test", drums="auto", max_speakers=32)

#: A key `DRUM_MAP` deliberately drops, so "dropped" and "given a sound" are
#: both reachable from one file.
_UNMAPPED_KEY = 60

# Default tempo is 500ms per beat over 480 ticks, so one millisecond is 0.96
# ticks. Spelled out because a held-note test that is quietly 30% short would
# still pass the wrong threshold.
_TICKS_PER_MS = 480 / 500.0


def _write(tmp_path, messages, name="control.mid"):
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.extend(messages)
    path = tmp_path / name
    mid.save(str(path))
    return path


def _write_midi(tmp_path, pairs, programs=None, name="control.mid", ticks=120):
    """A file of back-to-back (channel, note) hits, one program change each."""
    messages = [
        mido.Message("program_change", channel=channel, program=program, time=0)
        for channel, program in sorted((programs or {}).items())
    ]
    for channel, note in pairs:
        messages.append(mido.Message("note_on", channel=channel, note=note, velocity=100, time=0))
        messages.append(
            mido.Message("note_off", channel=channel, note=note, velocity=0, time=ticks)
        )
    return _write(tmp_path, messages, name)


def _held_note_midi(tmp_path, held_ms, name="held.mid"):
    ticks = round(held_ms * _TICKS_PER_MS)
    return _write(
        tmp_path,
        [
            mido.Message("program_change", channel=0, program=40, time=0),
            mido.Message("note_on", channel=0, note=67, velocity=100, time=0),
            mido.Message("note_off", channel=0, note=67, velocity=0, time=ticks),
        ],
        name,
    )


def _lopsided_layers_midi(tmp_path, name="lopsided.mid"):
    """Three overlapping notes on channel 0, one alone on channel 1.

    Deliberately uneven, so the largest single layer (3) and the running total
    across layers (4) are different numbers.
    """
    messages = [mido.Message("program_change", channel=c, program=40, time=0) for c in (0, 1)]
    for note in (60, 62, 64):
        messages.append(mido.Message("note_on", channel=0, note=note, velocity=100, time=0))
    for i, note in enumerate((60, 62, 64)):
        messages.append(
            mido.Message("note_off", channel=0, note=note, velocity=0, time=480 if i == 0 else 0)
        )
    messages.append(mido.Message("note_on", channel=1, note=67, velocity=100, time=0))
    messages.append(mido.Message("note_off", channel=1, note=67, velocity=0, time=480))
    return _write(tmp_path, messages, name)


# ---- muting ----


def test_a_muted_channel_contributes_no_notes(tmp_path):
    mid = _write_midi(tmp_path, [(0, 60), (1, 67)], programs={0: 0, 1: 40})
    notes, _ = parse_notes(mid, drums=False, channel_mutes={1})
    assert {n.chan for n in notes} == {0}


def test_a_muted_note_is_not_a_dropped_note(tmp_path):
    """`dropped` means the palette had no sound for a note -- a problem worth
    reporting. A muted note was asked for, so counting it there would put a
    decision the user just made into the one number that means something is
    wrong, and the window would report a fault every time someone used a mute.
    """
    mid = _write_midi(tmp_path, [(9, 36), (9, _UNMAPPED_KEY)] * 3)
    _, loud = parse_notes(mid, drums=True)
    assert loud["dropped"] == 3, "the unmapped key is supposed to drop when it plays"

    notes, muted = parse_notes(mid, drums=True, channel_mutes={9})
    assert notes == []
    assert muted["dropped"] == 0


def test_muting_every_channel_leaves_no_notes_at_all():
    notes, stats = parse_notes(TINY_MIDI, channel_mutes=set(range(16)))
    assert notes == []
    assert stats["dropped"] == 0


def test_an_empty_mute_set_parses_exactly_what_no_mute_set_parses():
    """The lever has to be inert when nobody has pulled it: the window passes
    it on every compile, including the first one before anything is chosen."""
    assert parse_notes(TINY_MIDI, channel_mutes=set())[0] == parse_notes(TINY_MIDI)[0]


# ---- unified track sound assignment ----


def test_an_exact_sound_wins_and_keeps_the_written_midi_pitch(tmp_path):
    mid = _write_midi(tmp_path, [(0, 48), (0, 72)], programs={0: 0})
    sound = palette.sounds_in_category("amb_air")[0]
    notes, stats = parse_notes(
        mid,
        drums=False,
        channel_families={0: "ins_violin"},
        channel_sounds={0: sound},
    )
    assert stats["dropped"] == 0
    assert {note.shader for note in notes} == {sound}
    assert {note.fam for note in notes} == {"amb_air"}
    assert [note.pitch for note in notes] == [48, 72]
    assert all(note.sustained for note in notes)


@pytest.mark.parametrize(
    ("catalog_looping", "sustained"),
    [(False, False), (True, True), (None, True)],
)
def test_a_full_game_exact_event_uses_catalog_loop_metadata(tmp_path, catalog_looping, sustained):
    mid = _write_midi(tmp_path, [(0, 60)], programs={0: 0})

    notes, _stats = parse_notes(
        mid,
        drums=False,
        channel_sounds={0: "Play_Wpn_Shotgun_Fire"},
        event_is_looping=lambda _name: catalog_looping,
    )

    assert notes[0].fam == "exact"
    assert notes[0].sustained is sustained


def test_exact_event_loop_metadata_is_read_once_per_channel_sound(tmp_path):
    sound = "Play_Wpn_Shotgun_Fire"
    mid = _write_midi(tmp_path, [(0, 60), (0, 62), (0, 64)], programs={0: 0})
    calls = []

    def event_is_looping(name):
        calls.append(name)
        return False

    notes, _ = parse_notes(
        mid,
        drums=False,
        channel_sounds={0: sound},
        event_is_looping=event_is_looping,
    )

    assert len(notes) == 3
    assert calls == [sound]


def test_a_pitched_family_selected_on_the_drum_channel_bypasses_the_kit(tmp_path):
    mid = _write_midi(tmp_path, [(9, 36), (9, 38)])
    index = palette.build_note_index()
    notes, _ = parse_notes(mid, drums=True, channel_families={9: "ins_piano"}, note_index=index)
    assert [note.shader for note in notes] == [
        palette.decl_for("ins_piano", 36, index),
        palette.decl_for("ins_piano", 38, index),
    ]
    assert all(note.fam == "ins_piano" for note in notes)
    assert {note.shader for note in notes}.isdisjoint(set(DRUM_MAP.values()))


# ---- per-drum-key sounds ----


def test_a_drum_key_can_be_given_a_different_sound(tmp_path):
    mid = _write_midi(tmp_path, [(9, 36)] * 8)
    notes, _ = parse_notes(mid, drums=True, drum_key_overrides={36: "play_noise_hat"})
    assert {n.shader for n in notes} == {"play_noise_hat"}
    assert DRUM_MAP[36] != "play_noise_hat", "the table has to disagree for this to prove anything"


def test_an_unmapped_key_given_a_sound_stops_being_counted_as_dropped(tmp_path):
    """`DRUM_MAP` drops exotic keys rather than guessing. Until now that was
    final: the note was gone and the count was all you got."""
    mid = _write_midi(tmp_path, [(9, _UNMAPPED_KEY)] * 8)
    notes, stats = parse_notes(mid, drums=True)
    assert notes == [] and stats["dropped"] == 8

    notes, stats = parse_notes(mid, drums=True, drum_key_overrides={_UNMAPPED_KEY: "play_clave1"})
    assert {n.shader for n in notes} == {"play_clave1"}
    assert stats["dropped"] == 0


def test_the_shader_table_does_not_overwrite_a_per_key_choice(tmp_path):
    """`drum_overrides` is keyed by resolved shader and was applied AFTER the
    per-key lookup, so it silently replaced whatever the user had just picked.
    It post-processes the TABLE's answer, not the user's."""
    mid = _write_midi(tmp_path, [(9, 36)] * 8)
    notes, _ = parse_notes(
        mid,
        drums=True,
        drum_overrides={"play_noise_clap": "play_noise_crash"},
        drum_key_overrides={36: "play_noise_clap"},
    )
    assert {n.shader for n in notes} == {"play_noise_clap"}


def test_the_shader_table_still_retimbres_what_the_table_itself_picked(tmp_path):
    """The precedence fix must not disable `drum_overrides` -- it is still the
    way to retimbre a whole kit without naming every key."""
    mid = _write_midi(tmp_path, [(9, 36)] * 8)
    notes, _ = parse_notes(mid, drums=True, drum_overrides={DRUM_MAP[36]: "play_noise_hat"})
    assert {n.shader for n in notes} == {"play_noise_hat"}


def test_a_muted_drum_channel_ignores_its_key_overrides(tmp_path):
    """Mute is checked first, so a key override on a silenced kit is not a way
    to smuggle notes back in."""
    mid = _write_midi(tmp_path, [(9, _UNMAPPED_KEY)] * 4)
    notes, stats = parse_notes(
        mid, drums=True, channel_mutes={9}, drum_key_overrides={_UNMAPPED_KEY: "play_clave1"}
    )
    assert notes == [] and stats["dropped"] == 0


# ---- statistics the engine limit justifies ----


def test_statistics_report_voice_pressure_and_expression_paths():
    """Pressure is peak simultaneous isolated voices, not total event count."""
    _, stats = compile_to_rawmap(TINY_MIDI)
    assert "long_sustains" in stats
    assert "peak_voices" in stats
    assert "shared_one_shots" in stats
    assert "expressive_one_shots" in stats
    assert "expressive_notes" in stats
    assert stats["max_speakers"] == 32


def test_max_speakers_is_echoed_so_peak_voices_can_be_read_against_something():
    """`peak_voices` alone says nothing: 8 is comfortable at 32 and saturated
    at 8. The number it is judged against travels with it."""
    _, stats = compile_to_rawmap(TINY_MIDI, max_speakers=7)
    assert stats["max_speakers"] == 7


def test_long_sustains_counts_notes_held_past_the_practical_target(tmp_path):
    """`docs/limits.md`: "notes held under about a second cut reliably"."""
    mid = _held_note_midi(tmp_path, held_ms=2000)
    _, stats = compile_to_rawmap(mid, channel_families={0: "ins_violin"})
    assert stats["long_sustains"] == 1


def test_a_note_under_the_target_is_not_a_long_sustain(tmp_path):
    mid = _held_note_midi(tmp_path, held_ms=400)
    _, stats = compile_to_rawmap(mid, channel_families={0: "ins_violin"})
    assert stats["sustained"] == 1
    assert stats["long_sustains"] == 0


def test_a_long_one_shot_is_not_a_long_sustain(tmp_path):
    """The whole point of the key. A decaying note holds no emitter slot, so
    however long it is written it cannot be the cause of a recycled note."""
    mid = _held_note_midi(tmp_path, held_ms=2000)
    _, stats = compile_to_rawmap(mid, channel_families={0: "ins_piano"})
    assert stats["decaying"] == 1
    assert stats["long_sustains"] == 0


def test_peak_voices_is_the_worst_single_layer_not_the_running_total(tmp_path):
    """Voices are allocated PER LAYER against `max_speakers`, so the total
    across layers can pass it while no layer is anywhere near it. Judging a map
    by the total warns about arrangements that thin nothing."""
    mid = _lopsided_layers_midi(tmp_path)
    _, stats = compile_to_rawmap(mid, channel_families={0: "ins_violin", 1: "ins_violin"})
    assert stats["voices"] == 4
    assert stats["peak_voices"] == 3


def test_peak_voices_reaching_max_speakers_is_what_says_a_layer_was_thinned(tmp_path):
    mid = _lopsided_layers_midi(tmp_path)
    _, stats = compile_to_rawmap(
        mid, channel_families={0: "ins_violin", 1: "ins_violin"}, max_speakers=2
    )
    assert stats["peak_voices"] == stats["max_speakers"] == 2


# ---- the byte gate ----


def test_compile_accepts_both_levers_without_moving_a_byte():
    """Adding parameters must not move output. The statistics dict is not
    serialized, so new keys there are safe; note ordering, field order and
    event construction are not, and all three are downstream of this call."""
    raw, _ = compile_to_rawmap(TINY_MIDI, channel_mutes=set(), drum_key_overrides={})
    assert raw == compile_to_rawmap(TINY_MIDI)[0]

    gated, _ = compile_to_rawmap(
        TINY_MIDI, channel_mutes=set(), drum_key_overrides={}, **_SCRATCH_PARAMS
    )
    assert gated == SCRATCH_GOLDEN.read_bytes()


def test_compiling_with_every_channel_muted_still_produces_a_loadable_map():
    """A window with a mute per row invites muting everything, and the answer
    has to be an empty song rather than a map the editor refuses."""
    raw, stats = compile_to_rawmap(TINY_MIDI, channel_mutes=set(range(16)))
    assert stats["notes"] == 0
    assert stats["peak_voices"] == 0
    assert b"idTarget_Timeline" in raw
