"""The window's state, and the sentences it is willing to say about a compile.

Three claims live here, and they fail in different ways.

The first is that the state is one thing. The rulers, the status bar and the
exported bytes all have to describe the same document at the same moment; a
session that recomputed each of them from whatever it happened to hold when
asked would show a ruler for one arrangement beside a warning about another.

The second is that a song is not a setup. Opening a second file must forget the
first file's instruments and keep the user's tuning, because those two are
answers to different questions -- and getting it backwards is silent either
way, which is why both directions are pinned.

The third is the warnings, which are the reason this module exists rather than
`compile_to_rawmap` being called directly. `docs/limits.md` names exactly two
quantities the engine limit touches, and neither is the event count. The test
at the bottom compiles a file of six hundred one-shots -- the arrangement an
event-count warning fires hardest on and the limit cannot touch at all -- and
demands silence.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import mido
import pytest

from snapmap_midi import paths
from snapmap_midi import settings as settings_module
from snapmap_midi.compile import compile_to_rawmap
from snapmap_midi.sound import palette
from snapmap_midi.ui import session as session_module
from snapmap_midi.ui.session import Session

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_MIDI = str(FIXTURES / "tiny.mid")

# Default tempo is 500ms per beat over 480 ticks, so one millisecond is 0.96
# ticks. Spelled out because a held-note test that is quietly 30% short would
# still pass the wrong threshold.
_TICKS_PER_MS = 480 / 500.0


def _midi(tmp_path, messages, name="song.mid") -> str:
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.extend(messages)
    path = tmp_path / name
    mid.save(str(path))
    return str(path)


def _hits(channel, note, count=1, ticks=120, program=None) -> list:
    """`count` back-to-back hits of one note, optionally naming an instrument."""
    messages = []
    if program is not None:
        messages.append(mido.Message("program_change", channel=channel, program=program, time=0))
    for _ in range(count):
        messages.append(mido.Message("note_on", channel=channel, note=note, velocity=100, time=0))
        messages.append(
            mido.Message("note_off", channel=channel, note=note, velocity=0, time=ticks)
        )
    return messages


def _kit(tmp_path, extra_key=None, extra_count=2) -> str:
    """A channel-9 part the percussion heuristic accepts, plus an exotic key."""
    messages = []
    for key in (36, 38, 42):
        messages.extend(_hits(9, key, count=4))
    if extra_key is not None:
        messages.extend(_hits(9, extra_key, count=extra_count))
    return _midi(tmp_path, messages, name="kit.mid")


def _dense(tmp_path) -> str:
    """One channel playing one note at a time, and one playing a three-note chord.

    Two layers of different widths, so the warning about running out of
    speakers has a channel to be wrong about.
    """
    messages = [
        mido.Message("program_change", channel=0, program=40, time=0),
        mido.Message("program_change", channel=3, program=40, time=0),
        mido.Message("note_on", channel=0, note=60, velocity=100, time=0),
        mido.Message("note_on", channel=3, note=60, velocity=100, time=0),
        mido.Message("note_on", channel=3, note=64, velocity=100, time=0),
        mido.Message("note_on", channel=3, note=67, velocity=100, time=0),
        mido.Message("note_off", channel=0, note=60, velocity=0, time=480),
        mido.Message("note_off", channel=3, note=60, velocity=0, time=0),
        mido.Message("note_off", channel=3, note=64, velocity=0, time=0),
        mido.Message("note_off", channel=3, note=67, velocity=0, time=0),
    ]
    return _midi(tmp_path, messages, name="dense.mid")


def _channel(session, number) -> dict:
    return [c for c in session.analysis_dict()["channels"] if c["channel"] == number][0]


def _warnings(session) -> list:
    return session.stats()["warnings"]


def _saved(tmp_path, doc) -> str:
    path = tmp_path / "settings.json"
    settings_module.save(doc, path)
    return str(path)


# ---- opening a song ----


def test_loading_a_song_keeps_its_analysis():
    session = Session()
    payload = session.load(TINY_MIDI)
    assert [c["channel"] for c in payload["channels"]] == [0, 1, 9]
    assert session.analysis_dict() == payload
    assert session.settings()["midi"] == TINY_MIDI


def test_a_song_that_is_not_there_is_a_plain_missing_file(tmp_path):
    """Named by `load`, so it raises. The remembered path in a settings file is
    the case that must not, and it is pinned separately below."""
    with pytest.raises(FileNotFoundError):
        Session().load(tmp_path / "nope.mid")


def test_a_failed_load_leaves_the_song_that_was_open_still_open(tmp_path):
    """The window has one visible state and no undo. Half-applying a failed open
    would leave it describing a file it never read."""
    session = Session(midi=TINY_MIDI)
    with pytest.raises(FileNotFoundError):
        session.load(tmp_path / "nope.mid")
    assert session.settings()["midi"] == TINY_MIDI
    assert session.analysis_dict()["path"] == TINY_MIDI


def test_opening_a_second_song_does_not_carry_the_first_song_s_instruments(tmp_path):
    """Channel 3's marimba following you into the next file silently retimbres a
    part you have never looked at. The channel numbers collide; the parts do
    not."""
    other = _midi(tmp_path, _hits(0, 60, program=0), name="other.mid")
    session = Session(midi=TINY_MIDI)
    session.apply(
        {"channels": {"0": {"family": "ins_marimba"}}, "drum_keys": {"36": "play_clave1"}}
    )
    session.load(other)
    assert session.settings()["channels"] == {}
    assert session.settings()["drum_keys"] == {}


def test_opening_a_second_song_keeps_the_tuning_the_button_and_the_folder(tmp_path):
    """These are about the user's setup rather than the song. Clearing them
    would make every new file a fresh argument with the same machine."""
    other = _midi(tmp_path, _hits(0, 60, program=0), name="other.mid")
    session = Session(midi=TINY_MIDI)
    session.apply({"button": "my-song", "out_dir": str(tmp_path), "tuning": {"max_speakers": 8}})
    session.load(other)
    doc = session.settings()
    assert doc["button"] == "my-song"
    assert doc["out_dir"] == str(tmp_path)
    assert doc["tuning"]["max_speakers"] == 8


# ---- workstation preview manifest ----


def test_preview_manifest_is_the_resolved_song_with_original_pitches():
    session = Session(midi=TINY_MIDI)
    manifest = session.preview_manifest()
    assert manifest["duration_ms"] > 0
    assert manifest["events"]
    assert manifest["sounds"] == sorted({event["sound"] for event in manifest["events"]})
    assert all(0 <= event["pitch"] <= 127 for event in manifest["events"])
    assert all("cut" in event for event in manifest["events"])


def test_preview_manifest_uses_an_exact_channel_sound_without_losing_note_positions():
    session = Session(midi=TINY_MIDI)
    sound = palette.sounds_in_category("amb_air")[0]
    session.apply({"channels": {"0": {"sound": sound}}})
    events = [event for event in session.preview_manifest()["events"] if event["channel"] == 0]
    assert events
    assert {event["sound"] for event in events} == {sound}
    assert {event["family"] for event in events} == {"amb_air"}
    assert all(event["sustained"] for event in events)


def test_preview_manifest_marks_speaker_reuse_as_a_hard_cut(tmp_path):
    session = Session(midi=_dense(tmp_path))
    session.apply({"tuning": {"max_speakers": 1}})
    events = [event for event in session.preview_manifest()["events"] if event["channel"] == 3]
    cut = [event for event in events if event["cut"]]
    assert len(events) == 3
    assert len(cut) == 2
    assert all(event["end"] == event["start"] for event in cut)


def test_preview_manifest_applies_polyphony_thinning_before_playback(tmp_path):
    session = Session(midi=_dense(tmp_path))
    session.apply({"tuning": {"max_poly": 1}})
    events = [event for event in session.preview_manifest()["events"] if event["channel"] == 3]
    assert [event["pitch"] for event in events] == [67]


# ---- opening a settings document ----


def test_a_settings_file_whose_song_has_moved_keeps_the_settings(tmp_path):
    """The song is one path; the tuning is an afternoon's work. Discarding the
    document because the file it names has been renamed throws away the only
    record of the session that produced it."""
    doc = settings_module.merge(
        settings_module.defaults(str(tmp_path / "gone.mid")),
        {"channels": {"0": {"family": "ins_tri"}}},
    )
    session = Session(settings_path=_saved(tmp_path, doc))
    assert session.settings()["channels"]["0"]["family"] == "ins_tri"
    assert session.analysis_dict() is None


def test_a_settings_file_that_names_a_song_that_is_there_opens_it(tmp_path):
    doc = settings_module.merge(
        settings_module.defaults(TINY_MIDI), {"channels": {"1": {"family": "ins_sine"}}}
    )
    session = Session(settings_path=_saved(tmp_path, doc))
    assert session.analysis_dict()["path"] == TINY_MIDI
    assert session.settings()["channels"]["1"]["family"] == "ins_sine"


def test_opening_a_settings_file_and_a_song_together_keeps_both(tmp_path):
    """`snapmap-midi ui song.mid --settings s.json` is one instruction, not two.
    Constructing is not reopening -- there is no earlier song whose instruments
    could leak in -- so the reset `load` performs would only throw away the file
    the user named on the same line."""
    doc = settings_module.merge(
        settings_module.defaults(), {"channels": {"1": {"family": "ins_sine"}}}
    )
    session = Session(midi=TINY_MIDI, settings_path=_saved(tmp_path, doc))
    assert session.settings()["midi"] == TINY_MIDI
    assert session.settings()["channels"]["1"]["family"] == "ins_sine"


def test_a_broken_settings_file_says_what_is_wrong_with_it(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"version": 1, "tuning": {"max_speakers": 0}}), encoding="utf-8")
    with pytest.raises(settings_module.SettingsError, match="max_speakers"):
        Session(settings_path=str(path))


# ---- changing the document ----


def test_apply_is_a_patch_and_not_a_replacement():
    session = Session(midi=TINY_MIDI)
    session.apply({"channels": {"0": {"family": "ins_marimba"}}})
    session.apply({"channels": {"0": {"muted": True}}})
    assert session.settings()["channels"]["0"] == {"family": "ins_marimba", "muted": True}


def test_a_refused_patch_changes_nothing():
    """`ins_string` is in SUSTAINED beside the violins and holds twelve
    unpitched effect samples. A session that had already stored it would compile
    the part to silence on the next dry run with nothing left to blame."""
    session = Session(midi=TINY_MIDI)
    before = session.settings()
    with pytest.raises(settings_module.SettingsError):
        session.apply({"channels": {"0": {"family": "ins_string"}}})
    with pytest.raises(settings_module.SettingsError):
        session.apply("nonsense")
    assert session.settings() == before


def test_the_document_handed_out_is_a_copy():
    """The bridge hands this straight to Javascript. A caller that edited the
    session's own dict would change what the next compile does without passing
    through `validate` -- and sharing one mutable document across threads
    defeats the lock that guards it."""
    session = Session(midi=TINY_MIDI)
    session.settings()["tuning"]["max_speakers"] = 1
    session.settings()["channels"]["0"] = {"family": "ins_tri", "muted": True}
    assert session.settings()["tuning"]["max_speakers"] == 32
    assert session.settings()["channels"] == {}


def test_turning_the_drums_off_re_reads_the_file():
    """Otherwise the row goes on offering drum keys for a channel the compiler
    has stopped routing through `DRUM_MAP`, and the window describes an
    instrument nothing plays."""
    session = Session(midi=TINY_MIDI)
    assert _channel(session, 9)["is_drums"] is True
    assert _channel(session, 9)["drum_keys"]

    session.apply({"drums": "off"})
    kit = _channel(session, 9)
    assert kit["is_drums"] is False
    assert kit["drum_keys"] == {}
    assert kit["auto_family"] is not None
    assert session.rulers()["9"] is not None


def test_changes_from_several_threads_all_land():
    """pywebview answers each Javascript call on its own thread, so two
    dropdowns changed in quick succession are two threads inside `apply`. An
    unguarded read-modify-write drops one of them with nothing to show that it
    happened."""
    session = Session(midi=TINY_MIDI)
    families = palette.pitched_families()[:8]
    ready = threading.Barrier(len(families))

    def change(index, family):
        ready.wait()
        session.apply({"channels": {str(index): {"family": family}}})

    threads = [threading.Thread(target=change, args=pair) for pair in enumerate(families)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert session.settings()["channels"] == {
        str(index): {"family": family, "muted": False} for index, family in enumerate(families)
    }


# ---- compiling ----


def test_the_note_index_is_built_once_and_handed_to_every_compile(monkeypatch):
    """Dropdowns fire immediately, so a re-parse per change is a re-parse per
    click. `compile_to_rawmap` already takes `note_index`; not passing it
    rebuilds the pitch index inside `parse_notes` on every keystroke."""
    session = Session(midi=TINY_MIDI)
    assert session._note_index is not None

    real = session_module.compile_to_rawmap
    seen = []

    def spy(*args, **kwargs):
        seen.append(kwargs.get("note_index"))
        return real(*args, **kwargs)

    monkeypatch.setattr(session_module, "compile_to_rawmap", spy)
    session.stats()
    session.apply({"channels": {"0": {"family": "ins_marimba"}}})
    session.stats()
    assert seen == [session._note_index, session._note_index]


def test_the_numbers_are_a_real_compile_of_the_document():
    """Not an estimate and not a cached summary. A dry run that disagreed with
    the export would be discovered in game, which is the loop this window exists
    to close."""
    session = Session(midi=TINY_MIDI)
    session.apply({"channels": {"1": {"family": "ins_marimba"}}})
    expected_raw, expected_stats = compile_to_rawmap(
        TINY_MIDI, **settings_module.to_compile_kwargs(session.settings())
    )
    raw, stats = session.compile()
    assert raw == expected_raw
    assert stats == expected_stats
    assert {k: v for k, v in session.stats().items() if k != "warnings"} == expected_stats


def test_asking_for_numbers_before_a_song_is_open_says_so():
    """A GUI user has no console to read a traceback in, and the window opens
    with no file at all."""
    session = Session()
    assert session.analysis_dict() is None
    assert session.rulers() == {}
    for call in (session.stats, session.export):
        with pytest.raises(ValueError, match="song"):
            call()


# ---- the rulers ----


def test_the_drum_channel_gets_no_ruler_and_every_other_channel_does():
    session = Session(midi=TINY_MIDI)
    rulers = session.rulers()
    assert set(rulers) == {"0", "1", "9"}
    assert rulers["9"] is None
    assert [cell["note"] for cell in rulers["0"]["cells"]] == [60]


def test_every_row_is_drawn_against_the_same_axis():
    """Rows are only comparable if they share one axis, and the axis is MIDI's
    own range rather than the file's. An axis derived from the notes present
    would move when a channel was muted, so the same part would sit somewhere
    else on the strip for a reason that has nothing to do with it."""
    session = Session(midi=TINY_MIDI)
    rulers = session.rulers()
    assert rulers["0"]["cell_width"] == rulers["1"]["cell_width"]
    assert rulers["1"]["cells"][0]["left"] == pytest.approx(48 / 127 * 100)


def test_the_ruler_tracks_the_family_the_user_chose():
    session = Session(midi=TINY_MIDI)
    automatic = session.rulers()["0"]["instrument"]
    session.apply({"channels": {"0": {"family": "ins_brass_bells"}}})
    chosen = session.rulers()["0"]
    assert chosen["instrument"]["left"] > automatic["left"]
    assert chosen["disjoint"] is True
    assert chosen["outside"] == 1


# ---- exporting ----


def test_export_writes_the_bytes_it_reports(tmp_path):
    out_dir = tmp_path / "not-there-yet"
    session = Session(midi=TINY_MIDI)
    session.apply({"out_dir": str(out_dir)})
    result = session.export()

    written = Path(result["destination"])
    assert written == (out_dir / paths.RAWMAP_NAME).resolve()
    assert written.read_bytes() == session.compile()[0]
    assert result["stats"]["notes"] == session.stats()["notes"]
    assert "warnings" in result["stats"]


def test_export_reports_what_it_replaced(tmp_path):
    """`rawmap.json` is a single global slot, and a button invites repeated use
    in a way a typed command did not. Overwriting somebody's other map without
    saying so is the failure; the answer is one word in the report."""
    session = Session(midi=TINY_MIDI)
    session.apply({"out_dir": str(tmp_path)})
    assert session.export()["replaced"] is False
    assert session.export()["replaced"] is True


def test_the_advice_tells_a_map_that_landed_where_the_loader_reads_how_to_play(
    tmp_path, monkeypatch
):
    """Three destinations, and they are genuinely different. Saying "it landed
    where the loader reads" about a file in some other folder is the same quiet
    wrong answer the retired `--out` flag produced."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    session = Session(midi=TINY_MIDI)

    session.apply({"out_dir": str(tmp_path / paths.LOADER_DIR_NAME)})
    assert "sh_rawmaps_on" in session.export()["advice"]

    session.apply({"out_dir": str(tmp_path / "elsewhere")})
    assert "move it there" in session.export()["advice"]


# ---- warnings ----


def test_the_automatic_family_is_warned_about_too():
    """The compiler's own guess can be the thing that is wrong: this file's
    channel 1 is a General MIDI Violin whose low note the violin family cannot
    reach. A warning that only fired on a family somebody had picked would stay
    silent on every file nobody had touched yet."""
    session = Session(midi=TINY_MIDI)
    assert [w for w in _warnings(session) if w.startswith("Channel 1")] == [
        "Channel 1 (Violin) plays C3-G4. ins_violin only reaches G3-E7, so 1 of its 2 "
        "notes moves to another octave, or to the nearest pitch the family has."
    ]


def test_a_warning_speaks_the_note_names_the_ruler_is_labelled_with():
    """The window labels its C-octave gridlines in note names, so a sentence
    that said "plays 48-67" made the reader convert between two vocabularies to
    find out whether it was about the row they were looking at. Counts stay
    counts: a number that means "how many" is not a pitch and must not be
    dressed as one."""
    session = Session(midi=TINY_MIDI)
    warning = [w for w in _warnings(session) if w.startswith("Channel 1")][0]
    assert "48" not in warning
    assert "55" not in warning
    assert "plays C3-G4" in warning
    assert "1 of its 2 notes" in warning


def test_a_muted_channel_is_not_warned_about():
    """Reporting that a channel you just silenced cannot reach its notes is
    noise about a decision already made. Unmuting it brings the sentence back,
    which is what proves the silence is the mute and not the absence of a
    problem."""
    session = Session(midi=TINY_MIDI)
    session.apply({"channels": {"0": {"family": "ins_brass_bells", "muted": True}}})
    assert not any("Channel 0" in w for w in _warnings(session))

    session.apply({"channels": {"0": {"muted": False}}})
    assert any("Channel 0" in w for w in _warnings(session))


def test_muting_everything_says_nothing_will_play():
    session = Session(midi=TINY_MIDI)
    session.apply({"channels": {str(c): {"muted": True} for c in (0, 1, 9)}})
    assert _warnings(session)[0] == "Nothing will play: all 3 channels are muted."


def test_an_unmapped_drum_key_names_the_unified_track_choices_that_fix_it(tmp_path):
    """`DRUM_MAP` drops the exotic keys rather than guessing at them, so this is
    the ordinary way a file loses notes. Percussion has no separate tab now, so
    the warning points to the channel assignment and advanced sidecar override."""
    session = Session(midi=_kit(tmp_path, extra_key=60))
    warning = [w for w in _warnings(session) if "Percussion keys" in w][0]
    assert warning.startswith("2 notes have no sound and will not play.")
    assert "Percussion keys 60 are unmapped" in warning
    assert "instrument set or exact sound" in warning

    session.apply({"drum_keys": {"60": "play_clave1"}})
    assert not any("no sound" in w for w in _warnings(session))


def test_a_family_that_cannot_reach_some_notes_names_how_many(tmp_path):
    """Both counts, because two notes out of three is a different decision from
    two out of two thousand and the ruler is the only other place that says
    so."""
    song = _midi(
        tmp_path,
        _hits(0, 30, program=0) + _hits(0, 40) + _hits(0, 100),
        name="range.mid",
    )
    session = Session(midi=song)
    session.apply({"channels": {"0": {"family": "ins_sine"}}})
    assert [w for w in _warnings(session) if w.startswith("Channel 0")] == [
        "Channel 0 (Acoustic Grand Piano) plays F#1-E7. ins_sine only reaches C2-G4, so 2 "
        "of its 3 notes move to another octave, or to the nearest pitch the family has."
    ]


def test_a_family_that_shares_no_note_with_the_channel_says_every_note_is_transposed():
    """Zero overlap is not a worse degree of overhang. The melody is gone, and a
    sentence about a proportion would read as a matter of degree."""
    session = Session(midi=TINY_MIDI)
    session.apply({"channels": {"0": {"family": "ins_brass_bells"}}})
    assert (
        "Channel 0 (Acoustic Grand Piano) shares no note with ins_brass_bells at all. "
        "Every note is transposed."
    ) in _warnings(session)


def test_three_range_warnings_are_still_three_sentences(tmp_path):
    messages = []
    for channel in range(3):
        messages.extend(_hits(channel, 20, program=0))
        messages.extend(_hits(channel, 100))
    session = Session(midi=_midi(tmp_path, messages, name="three.mid"))
    session.apply({"channels": {str(c): {"family": "ins_sine"} for c in range(3)}})
    assert len([w for w in _warnings(session) if w.startswith("Channel")]) == 3


def test_more_than_three_range_warnings_collapse_to_the_worst_one(tmp_path):
    """Sixteen near-identical sentences in a status bar is not information, and
    the per-row ruler already carries the detail. What the line has to keep is
    which channel is worst and how much else is wrong."""
    messages = []
    for channel in range(5):
        messages.extend(_hits(channel, 20, count=channel + 1, program=0))
        messages.extend(_hits(channel, 100))
    session = Session(midi=_midi(tmp_path, messages, name="wide.mid"))
    session.apply({"channels": {str(c): {"family": "ins_sine"} for c in range(5)}})

    lines = [w for w in _warnings(session) if w.startswith("Channel")]
    assert len(lines) == 1
    assert lines[0].startswith("Channel 4 (Acoustic Grand Piano) plays G#0-E7.")
    assert "4 other channels" in lines[0]


def test_a_note_held_past_a_second_is_the_warning_the_engine_limit_justifies(tmp_path):
    """`docs/limits.md` gives one practical target: notes held under about a
    second cut reliably. Capping the sustain is the lever the sentence names,
    so it has to be the lever that removes it."""
    held = round(2000 * _TICKS_PER_MS)
    song = _midi(tmp_path, _hits(0, 67, ticks=held, program=40), name="held.mid")
    session = Session(midi=song)

    warning = [w for w in _warnings(session) if "sustained notes hold" in w][0]
    assert warning.startswith("1 sustained notes hold longer than a second.")
    assert "recycle the emitter" in warning

    session.apply({"tuning": {"cap_sustain_ms": 500}})
    assert not any("sustained notes hold" in w for w in _warnings(session))


def test_running_out_of_speakers_is_reported(tmp_path):
    """Voices are allocated per layer against `max_speakers`, and past it
    `allocate_voices` steals the voice that frees earliest -- so the note it
    stole from is truncated. Nothing in the map says so."""
    song = _midi(
        tmp_path,
        [
            mido.Message("program_change", channel=0, program=40, time=0),
            mido.Message("note_on", channel=0, note=60, velocity=100, time=0),
            mido.Message("note_on", channel=0, note=64, velocity=100, time=0),
            mido.Message("note_off", channel=0, note=60, velocity=0, time=480),
            mido.Message("note_off", channel=0, note=64, velocity=0, time=0),
        ],
        name="dense.mid",
    )
    session = Session(midi=song)
    session.apply({"tuning": {"max_speakers": 1}})
    assert any("Channel 0 (Violin) used all 1 speakers" in w for w in _warnings(session))

    session.apply({"tuning": {"max_speakers": 32}})
    assert not any("speakers" in w for w in _warnings(session))


def test_the_channel_that_ran_out_of_speakers_is_the_one_that_is_named(tmp_path):
    """ "The busiest channel" was all the sentence could say, because
    `compile_to_rawmap` reports the worst layer's voice count and not which
    layer it was -- so the one thing the reader needs in order to act, which row
    to go and thin, was the one thing missing. Channel 0 plays one note at a
    time and channel 3 plays a triad; only one of them is against the ceiling.
    """
    session = Session(midi=_dense(tmp_path))
    session.apply({"tuning": {"max_speakers": 2}})
    assert [w for w in _warnings(session) if "speakers" in w] == [
        "Channel 3 (Violin) used all 2 speakers, so its densest passages were thinned. "
        "Raise max speakers, or cap the polyphony."
    ]


def test_capping_the_sustain_still_names_the_right_channel(tmp_path):
    """The layers are rebuilt here to find out which one peaked, and a cap
    shortens notes before they are allocated -- so a rebuild that ignored the
    caps would count a concurrency the compile never had."""
    session = Session(midi=_dense(tmp_path))
    session.apply({"tuning": {"max_speakers": 2, "cap_sustain_ms": 50}})
    assert any("Channel 3 (Violin) used all 2 speakers" in w for w in _warnings(session))


def test_a_layer_count_that_disagrees_with_the_compile_names_no_channel(tmp_path, monkeypatch):
    """The rebuilt layers are a hypothesis, and the compile's own `peak_voices`
    is the fact. When the two disagree -- which is what a change to how the
    compiler thins or caps would look like from here -- the sentence goes back
    to naming no channel rather than naming the wrong one."""
    session = Session(midi=_dense(tmp_path))
    session.apply({"tuning": {"max_speakers": 2}})
    monkeypatch.setattr(session_module, "allocate_voices", lambda notes, cap: 1)
    assert any("The busiest channel used all 2 speakers" in w for w in _warnings(session))


def test_a_file_of_one_shots_that_cannot_hit_the_limit_is_not_warned_about(tmp_path):
    """The regression this whole warning set exists to undo. An earlier draft
    warned on total event count; `docs/limits.md` says a decaying sound holds no
    emitter slot and is immune, and that only the sustained path is exposed. Six
    hundred drum hits is the arrangement that number screams about and the limit
    cannot touch, and the sparse pad it stays silent on is the one that will."""
    messages = []
    for key in (36, 38, 42):
        messages.extend(_hits(9, key, count=200))
    session = Session(midi=_midi(tmp_path, messages, name="busy.mid"))

    report = session.stats()
    assert report["events"] > 400
    assert report["long_sustains"] == 0
    assert report["warnings"] == []
