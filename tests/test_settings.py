"""The settings document: everything a compile should do, in one editable file.

Three separate claims live here.

The first is that the defaults are the compiler's own. The window opens on this
document before the user has touched anything, so a default that disagrees with
`compile_to_rawmap` means opening the window and pressing export silently
produces a different map from typing the command -- and nothing anywhere would
say so. The contract test at the bottom settles it in bytes.

The second is that a patch is a patch. The window sends what changed, one field
at a time, so "mute channel 1" must not take channel 1's instrument with it and
"cap the sustain" must not reset the release. The exceptions are `drum_keys`
and `family_caps`, which are replaced wholesale because that is the only
spelling of "clear this entry" the format has.

The third is that a hand edit fails loudly. This file sits beside the song and
is meant to be opened in an editor, so its failure modes are hand-edit failure
modes: a family that compiles to silence, a lever that no longer exists, and
`{"channels": {"0": "ins_piano"}}` -- the shape everyone writes first.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from snapmap_midi import settings
from snapmap_midi.compile import compile_to_rawmap
from snapmap_midi.music.gm import DRUM_MAP
from snapmap_midi.sound import palette

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_MIDI = FIXTURES / "tiny.mid"

#: A looping ambience, and the reason the drum pool is two categories rather
#: than "everything unpitched". A loop fired as a one-shot is never stopped.
_A_LOOP = "play_amb_scape_wind_breathy_2d_lp"


def _patch(patch, base=None) -> dict:
    """A document with one change applied, the way the window sends them."""
    return settings.merge(settings.defaults() if base is None else base, patch)


# ---- the defaults are the compiler's own ----


def test_every_tuning_lever_defaults_to_what_the_compiler_defaults_to():
    """Read out of the compiler's signature rather than typed in twice.

    A default that drifts is invisible: the window opens, the user changes one
    unrelated dropdown, and the export differs from the command line for a
    lever nobody touched. Comparing against the signature means the two cannot
    disagree without this failing.
    """
    compiler = inspect.signature(compile_to_rawmap).parameters
    doc = settings.defaults()

    assert doc["button"] == compiler["button_name"].default
    assert doc["drums"] == compiler["drums"].default
    for lever, value in doc["tuning"].items():
        expected = compiler[lever].default
        if expected is None and value in ([], {}):
            # The compiler spells "this lever is off" as None; the document
            # spells it as an empty container, so JSON has something to hold.
            continue
        assert value == expected, lever


def test_the_document_carries_its_own_version():
    assert settings.defaults()["version"] == settings.SETTINGS_VERSION


def test_the_named_defaults_are_the_ones_the_docs_promise():
    """Spelled out as well as derived, so a signature change that moves both
    at once still trips something."""
    tuning = settings.defaults()["tuning"]
    assert tuning["master_volume_db"] == 0
    assert tuning["max_speakers"] == 32
    assert tuning["release_s"] == 0.1
    assert tuning["hard_stop"] is False
    assert tuning["max_poly"] is None
    assert tuning["cap_sustain_ms"] is None
    assert tuning["bass_pitch"] == 78
    assert tuning["bass_cap_ms"] is None
    assert tuning["decaying_families"] == []
    assert tuning["family_caps"] == {}


def test_max_events_is_not_a_setting_at_all():
    """`compile.py` implements it as `decaying_events[:max_events]`, which
    truncates the one-shot list in TIME order -- the drums simply stop partway
    through the song. Behind a slider that reads as a density control, it is a
    trap. It stays a command-line flag.
    """
    assert "max_events" not in settings.defaults()["tuning"]
    with pytest.raises(settings.SettingsError, match="max_events"):
        _patch({"tuning": {"max_events": 100}})


def test_a_song_can_be_named_when_the_document_is_built():
    assert settings.defaults(TINY_MIDI)["midi"] == str(TINY_MIDI)
    assert settings.defaults()["midi"] is None


def test_two_documents_do_not_share_their_containers():
    """A shallow copy of the tuning table would put the SAME empty list and the
    same empty dict inside every document the process ever builds, so one
    session's decaying families would appear in the next one's."""
    first, second = settings.defaults(), settings.defaults()
    first["tuning"]["decaying_families"].append("ins_violin")
    first["tuning"]["family_caps"]["ins_flute"] = 100
    first["channels"]["0"] = {"family": "ins_tri", "muted": False}
    assert second["tuning"]["decaying_families"] == []
    assert second["tuning"]["family_caps"] == {}
    assert second["channels"] == {}


# ---- the file ----


def test_a_document_survives_the_trip_to_disk(tmp_path):
    doc = _patch(
        {
            "channels": {"0": {"family": "ins_marimba"}, "1": {"muted": True}},
            "drum_keys": {"38": "play_noise_clap"},
            "tuning": {"max_speakers": 8, "decaying_families": ["ins_violin"]},
        },
        settings.defaults(TINY_MIDI),
    )
    path = tmp_path / "song.mid.snapmap.json"
    settings.save(doc, path)
    assert settings.load(path) == doc


def test_the_file_is_one_a_human_can_edit(tmp_path):
    """It is the only record of an afternoon's tuning and it lives beside the
    song, so it will be opened in an editor. One long line is not a file
    anybody edits; it is a file they overwrite."""
    path = tmp_path / "s.json"
    settings.save(settings.defaults(TINY_MIDI), path)
    text = path.read_text(encoding="utf-8")
    assert "\n  " in text
    assert text.count("\n") >= len(settings.defaults())
    assert text.endswith("\n")
    assert json.loads(text)["version"] == settings.SETTINGS_VERSION


def test_saving_refuses_a_document_that_could_not_be_loaded_back(tmp_path):
    """Writing an invalid document means the failure surfaces on the NEXT
    session, against a file the tool wrote itself, with nothing to point at."""
    path = tmp_path / "s.json"
    with pytest.raises(settings.SettingsError):
        settings.save({**settings.defaults(), "drums": "sometimes"}, path)
    assert not path.exists()


def test_a_settings_file_that_is_not_json_names_itself(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json at all", encoding="utf-8")
    with pytest.raises(settings.SettingsError, match="broken.json"):
        settings.load(path)


def test_a_settings_file_that_is_not_there_names_itself(tmp_path):
    with pytest.raises(settings.SettingsError, match="gone.json"):
        settings.load(tmp_path / "gone.json")


def test_the_sidecar_sits_beside_the_song():
    """Persistence with no dialog and no "where did I put that file"."""
    assert settings.sidecar_path("D:/songs/bach.mid").name == "bach.mid.snapmap.json"
    assert settings.sidecar_path(TINY_MIDI).parent == TINY_MIDI.parent


def test_the_sidecar_keeps_the_song_s_extension():
    """`bach.mid` and `bach.midi` are two different songs. Replacing the
    extension instead of appending to it would give them one settings file and
    silently apply the first one's instruments to the second."""
    assert settings.sidecar_path("a/bach.mid") != settings.sidecar_path("a/bach.midi")


# ---- refusing what a hand edit produces ----


def test_an_unknown_top_level_key_names_itself():
    with pytest.raises(settings.SettingsError, match="tempo"):
        settings.validate({**settings.defaults(), "tempo": 120})


def test_an_unknown_tuning_lever_names_itself():
    """A lever name that no longer exists reads as applied and does nothing,
    which is the quiet wrong answer this whole codebase is arranged against."""
    doc = settings.defaults()
    doc["tuning"]["max_speaker"] = 8
    with pytest.raises(settings.SettingsError, match="max_speaker"):
        settings.validate(doc)


def test_a_document_from_a_later_build_is_refused_by_number():
    """The version exists so a document this build does not understand is
    refused rather than half-read."""
    with pytest.raises(settings.SettingsError, match=str(settings.SETTINGS_VERSION + 1)):
        settings.validate({**settings.defaults(), "version": settings.SETTINGS_VERSION + 1})


def test_a_version_one_document_migrates_without_inventing_expression():
    old = settings.defaults()
    old["version"] = 1
    old.pop("notes")
    migrated = settings.validate(old)
    assert migrated["version"] == settings.SETTINGS_VERSION
    assert migrated["notes"] == {}
    assert migrated["tuning"]["master_volume_db"] == 0


def test_a_version_two_document_migrates_with_neutral_master_volume():
    old = settings.defaults()
    old["version"] = 2
    old["tuning"].pop("master_volume_db")

    migrated = settings.validate(old)

    assert migrated["version"] == settings.SETTINGS_VERSION
    assert migrated["tuning"]["master_volume_db"] == 0


def test_a_version_three_document_migrates_note_pitch_and_relative_volume():
    old = settings.defaults()
    old["version"] = 3
    old["notes"] = {"0:60:1": {"transpose": -12, "volume_db": 3}}

    migrated = settings.validate(old)
    assert migrated["version"] == settings.SETTINGS_VERSION
    assert migrated["notes"] == {"0:60:1": {"pitch_offset": -12, "volume_trim_db": 3}}


def test_a_version_four_relative_volume_migrates_without_changing_meaning():
    old = settings.defaults()
    old["version"] = 4
    old["notes"] = {"0:60:1": {"volume_db": -7}}

    migrated = settings.validate(old)

    assert migrated["version"] == settings.SETTINGS_VERSION
    assert migrated["notes"] == {"0:60:1": {"volume_trim_db": -7}}


def test_version_three_preserves_an_existing_relative_follow_choice():
    old = settings.defaults()
    old["version"] = 3
    sound = palette.sounds_in_category("amb_air")[0]
    old["channels"] = {
        "0": {
            "sound": sound,
            "pitch_follow": True,
            "root_midi": 60,
            "root_confidence": 0,
            "root_source": "relative",
        }
    }

    migrated = settings.validate(old)
    channel = migrated["channels"]["0"]
    assert channel["pitch_follow"] is True
    assert channel["root_source"] == "relative"
    assert channel["soloed"] is False


def test_a_channel_entry_that_is_not_a_mapping_is_a_clean_error():
    """`{"channels": {"0": "ins_piano"}}` is the obvious hand-edit mistake.
    Running `set()` over the string reports `unknown channel setting(s): _, a,
    e, i, n, o, p, s`, which describes nothing anybody typed."""
    with pytest.raises(settings.SettingsError, match="channel 0"):
        settings.validate({**settings.defaults(), "channels": {"0": "ins_piano"}})


def test_merge_refuses_a_patch_that_is_not_a_mapping():
    with pytest.raises(settings.SettingsError):
        settings.merge(settings.defaults(), {"tuning": 3})
    with pytest.raises(settings.SettingsError):
        settings.merge(settings.defaults(), "nonsense")
    with pytest.raises(settings.SettingsError):
        settings.merge(settings.defaults(), {"channels": ["ins_piano"]})


def test_a_family_that_cannot_play_a_pitch_is_refused():
    """`decl_for` returns None for every note of an unpitched category, so the
    channel drops out entirely: a map that loads, runs, and plays nothing where
    the part used to be."""
    for family in ("ins_noise", "amb_air", "no_such_family"):
        with pytest.raises(settings.SettingsError, match=family):
            _patch({"channels": {"0": {"family": family}}})


def test_ins_string_is_refused_like_any_other_silent_family():
    """The trap: named like an instrument, listed in `SUSTAINED` beside the
    violins, and holding twelve unpitched effect samples."""
    with pytest.raises(settings.SettingsError, match="ins_string"):
        _patch({"channels": {"0": {"family": "ins_string"}}})


def test_a_channel_may_choose_any_exact_sound_in_the_shipped_palette():
    sound = palette.sounds_in_category("amb_air")[0]
    doc = _patch({"channels": {"0": {"sound": sound}}})
    assert doc["channels"]["0"] == {
        "family": None,
        "sound": sound,
        "muted": False,
        "soloed": False,
    }


def test_an_exact_sound_root_profile_is_normalized_and_forwarded():
    sound = palette.sounds_in_category("ins_piano")[0]
    doc = _patch(
        {
            "channels": {
                "0": {
                    "sound": sound,
                    "pitch_follow": True,
                    "root_midi": 60.25,
                    "root_confidence": 0.88,
                    "root_source": "detected",
                }
            }
        }
    )
    assert doc["channels"]["0"] == {
        "family": None,
        "sound": sound,
        "muted": False,
        "soloed": False,
        "pitch_follow": True,
        "root_midi": 60.25,
        "root_confidence": 0.88,
        "root_source": "detected",
    }
    assert settings.to_compile_kwargs(doc)["channel_pitch_profiles"][0] == {
        "pitch_follow": True,
        "root_midi": 60.25,
        "root_confidence": 0.88,
        "root_source": "detected",
    }


def test_relative_reference_is_not_mislabeled_as_an_acoustic_root():
    sound = palette.sounds_in_category("amb_air")[0]
    doc = _patch(
        {
            "channels": {
                "0": {
                    "sound": sound,
                    "pitch_follow": True,
                    "root_midi": 66,
                    "root_confidence": 0,
                    "root_source": "relative",
                }
            }
        }
    )
    assert doc["channels"]["0"]["root_source"] == "relative"
    assert doc["channels"]["0"]["root_confidence"] == 0.0


def test_pitch_follow_requires_a_root():
    sound = palette.sounds_in_category("ins_piano")[0]
    with pytest.raises(settings.SettingsError, match="root_midi"):
        _patch({"channels": {"0": {"sound": sound, "pitch_follow": True}}})


def test_per_note_expression_preserves_an_explicit_zero_volume_and_is_forwarded():
    doc = _patch(
        {
            "notes": {
                "0:60:1": {"pitch_offset": -12, "volume_db": 3},
                "0:60:2": {"pitch_offset": 0, "volume_db": 0},
            }
        }
    )
    assert doc["notes"] == {
        "0:60:1": {"pitch_offset": -12, "volume_db": 3},
        "0:60:2": {"volume_db": 0},
    }
    kwargs = settings.to_compile_kwargs(doc)
    assert kwargs["note_overrides"] == doc["notes"]
    assert kwargs["note_overrides"] is not doc["notes"]


@pytest.mark.parametrize(
    "note_id",
    ["0:60", "16:60:1", "0:128:1", "0:60:0", "0:60:01", 123],
)
def test_invalid_note_ids_are_refused_by_name(note_id):
    with pytest.raises(settings.SettingsError, match="note"):
        _patch({"notes": {note_id: {"pitch_offset": 1}}})


def test_note_expression_stays_inside_snapmap_limits():
    with pytest.raises(settings.SettingsError, match="pitch_offset"):
        _patch({"notes": {"0:60:1": {"pitch_offset": 25}}})
    with pytest.raises(settings.SettingsError, match="volume_db"):
        _patch({"notes": {"0:60:1": {"volume_db": -61}}})
    with pytest.raises(settings.SettingsError, match="volume_trim_db"):
        _patch({"notes": {"0:60:1": {"volume_trim_db": 21}}})


def test_absolute_and_legacy_note_volume_cannot_be_combined():
    with pytest.raises(settings.SettingsError, match="cannot both be set"):
        _patch({"notes": {"0:60:1": {"volume_db": 0, "volume_trim_db": -3}}})


def test_a_full_game_play_event_is_valid_without_reading_the_install():
    sound = "Play_Wpn_Shotgun_Fire"
    doc = _patch({"channels": {"0": {"sound": sound}}})
    assert doc["channels"]["0"]["sound"] == sound


@pytest.mark.parametrize(
    "sound",
    ["stop_wpn_shotgun_fire", "../Play_escape", "Play_", "Play_" + "x" * 60],
)
def test_an_invalid_exact_event_identifier_is_refused(sound):
    with pytest.raises(settings.SettingsError, match="valid DOOM Play_ event"):
        _patch({"channels": {"0": {"sound": sound}}})


def test_a_channel_cannot_choose_a_family_and_an_exact_sound_together():
    sound = palette.sounds_in_category("ins_piano")[0]
    with pytest.raises(settings.SettingsError, match="not both"):
        _patch({"channels": {"0": {"family": "ins_piano", "sound": sound}}})


def test_a_channel_outside_the_sixteen_is_refused():
    with pytest.raises(settings.SettingsError, match="channel"):
        settings.validate({**settings.defaults(), "channels": {"16": {}}})


def test_muted_has_to_be_true_or_false():
    with pytest.raises(settings.SettingsError, match="muted"):
        _patch({"channels": {"0": {"muted": "yes"}}})


def test_soloed_has_to_be_true_or_false():
    with pytest.raises(settings.SettingsError, match="soloed"):
        _patch({"channels": {"0": {"soloed": "yes"}}})


def test_an_unknown_channel_setting_names_itself():
    with pytest.raises(settings.SettingsError, match="volume"):
        _patch({"channels": {"0": {"volume": 3}}})


def test_the_drums_mode_is_one_of_three_words():
    with pytest.raises(settings.SettingsError, match="sometimes"):
        _patch({"drums": "sometimes"})


def test_a_drum_key_must_name_a_percussion_sound():
    """A pitched sound plays one fixed note under every hit."""
    with pytest.raises(settings.SettingsError, match="play_pianoc4"):
        _patch({"drum_keys": {"38": "play_pianoc4"}})


def test_a_looping_ambience_is_refused_as_a_drum_sound():
    """A loop fired as a one-shot is never told to stop, so it holds its
    emitter open until the engine recycles the slot out from under something
    else -- the exact failure the compiler schedules its whole output around."""
    assert _A_LOOP in palette.sounds_in_category("amb_air"), "the palette moved"
    with pytest.raises(settings.SettingsError, match=_A_LOOP):
        _patch({"drum_keys": {"38": _A_LOOP}})


def test_every_sound_the_table_already_uses_can_be_written_back():
    """Otherwise a user cannot put a key back the way they found it."""
    for key, sound in DRUM_MAP.items():
        assert settings.validate({**settings.defaults(), "drum_keys": {str(key): sound}})


def test_a_drum_key_outside_the_midi_range_is_refused():
    with pytest.raises(settings.SettingsError, match="drum key"):
        _patch({"drum_keys": {"200": "play_noise_hat"}})


# ---- bounds on the levers ----


@pytest.mark.parametrize("value", [-61, 21, "6", 1.5, True])
def test_master_volume_outside_the_snapmap_db_range_is_refused(value):
    with pytest.raises(settings.SettingsError, match="master_volume_db"):
        _patch({"tuning": {"master_volume_db": value}})


def test_master_volume_is_persisted_and_forwarded_to_the_compiler():
    doc = _patch({"tuning": {"master_volume_db": 12}})

    assert doc["tuning"]["master_volume_db"] == 12
    assert settings.to_compile_kwargs(doc)["master_volume_db"] == 12
    assert _patch({"tuning": {"master_volume_db": -60}})["tuning"]["master_volume_db"] == -60


@pytest.mark.parametrize("value", [0, -1, 129, "32", 3.5, True])
def test_max_speakers_outside_its_bounds_is_refused(value):
    """At zero, `allocate_voices` reaches `min(range(0), ...)` and raises
    `ValueError: min() arg is an empty sequence` from four calls inside the
    compiler, which is not a sentence about a setting."""
    with pytest.raises(settings.SettingsError, match="max_speakers"):
        _patch({"tuning": {"max_speakers": value}})


def test_max_speakers_at_its_bounds_is_accepted():
    assert _patch({"tuning": {"max_speakers": 1}})["tuning"]["max_speakers"] == 1
    assert _patch({"tuning": {"max_speakers": 128}})["tuning"]["max_speakers"] == 128


def test_a_release_that_runs_backwards_is_refused():
    """It is written straight into the map as the fade's duration in seconds."""
    with pytest.raises(settings.SettingsError, match="release_s"):
        _patch({"tuning": {"release_s": -0.5}})


def test_a_release_longer_than_the_song_is_refused():
    with pytest.raises(settings.SettingsError, match="release_s"):
        _patch({"tuning": {"release_s": 60.0}})


def test_a_whole_number_release_is_still_a_number():
    """JSON writes `0` for a float that happens to be whole, and reads it back
    as an int. Refusing it would make a file the tool wrote unloadable."""
    assert _patch({"tuning": {"release_s": 0}})["tuning"]["release_s"] == 0


@pytest.mark.parametrize("value", [-1, 128, 78.5, "78"])
def test_bass_pitch_stays_inside_the_midi_range(value):
    """It is compared against `shader_pitch`, which is a MIDI note number."""
    with pytest.raises(settings.SettingsError, match="bass_pitch"):
        _patch({"tuning": {"bass_pitch": value}})


def test_bass_pitch_reaches_both_ends_of_the_range():
    assert _patch({"tuning": {"bass_pitch": 0}})["tuning"]["bass_pitch"] == 0
    assert _patch({"tuning": {"bass_pitch": 127}})["tuning"]["bass_pitch"] == 127


@pytest.mark.parametrize("lever", ["max_poly", "cap_sustain_ms", "bass_cap_ms"])
def test_an_optional_lever_takes_null_or_a_positive_number(lever):
    """None is how every one of these spells "off". Zero is not the same
    thing: `thin_polyphony(notes, 0)` keeps nothing at all, and a zero cap
    truncates every note to nothing."""
    assert _patch({"tuning": {lever: None}})["tuning"][lever] is None
    assert _patch({"tuning": {lever: 400}})["tuning"][lever] == 400
    with pytest.raises(settings.SettingsError, match=lever):
        _patch({"tuning": {lever: 0}})


def test_sound_behavior_accepts_every_real_palette_category_and_refuses_unknown_ones():
    """Exact sound assignments retain their category, including unpitched
    ambience and effects, so behavior controls must accept all 24 categories."""
    doc = _patch(
        {
            "tuning": {
                "family_caps": {"ins_noise": 400},
                "decaying_families": ["ins_string"],
            }
        }
    )
    assert doc["tuning"]["family_caps"] == {"ins_noise": 400}
    assert doc["tuning"]["decaying_families"] == ["ins_string"]

    with pytest.raises(settings.SettingsError, match="no_such_category"):
        _patch({"tuning": {"family_caps": {"no_such_category": 400}}})
    with pytest.raises(settings.SettingsError, match="no_such_category"):
        _patch({"tuning": {"decaying_families": ["no_such_category"]}})


def test_decaying_families_has_to_be_a_list_of_names():
    with pytest.raises(settings.SettingsError, match="decaying_families"):
        _patch({"tuning": {"decaying_families": "ins_violin"}})


# ---- a patch is a patch ----


def test_changing_one_lever_leaves_the_others_alone():
    doc = _patch({"tuning": {"max_speakers": 8}})
    assert doc["tuning"]["max_speakers"] == 8
    assert doc["tuning"]["release_s"] == 0.1
    assert doc["tuning"]["bass_pitch"] == 78


def test_muting_a_channel_does_not_clear_its_instrument():
    """The window sends what changed. `{"channels": {"1": {"muted": true}}}`
    replacing the whole entry would silently drop the family the user picked a
    moment earlier, and the ruler would jump back to the automatic choice."""
    base = _patch({"channels": {"1": {"family": "ins_marimba"}}})
    doc = _patch({"channels": {"1": {"muted": True}}}, base)
    assert doc["channels"]["1"] == {"family": "ins_marimba", "muted": True, "soloed": False}


def test_changing_one_channel_leaves_the_others_alone():
    base = _patch({"channels": {"0": {"family": "ins_marimba"}, "3": {"family": "ins_tri"}}})
    doc = _patch({"channels": {"3": {"muted": True}}}, base)
    assert doc["channels"]["0"]["family"] == "ins_marimba"
    assert doc["channels"]["3"]["family"] == "ins_tri"


def test_a_channel_can_be_returned_to_the_automatic_family():
    """Without this there is no way back to the automatic choice short of
    reopening the file."""
    base = _patch({"channels": {"0": {"family": "ins_marimba"}}})
    doc = _patch({"channels": {"0": {"family": None}}}, base)
    assert doc["channels"]["0"]["family"] is None
    assert settings.to_compile_kwargs(doc)["channel_families"] == {}


def test_the_drum_map_is_replaced_wholesale_because_that_is_how_a_key_is_cleared():
    """Validation demands a real sound name, so `null` cannot mean "put this
    key back to the table's answer", and under a deep merge nothing else could
    either -- every patch would only ever add. Sending the map minus one entry
    is the only spelling of "clear it" that exists."""
    base = _patch({"drum_keys": {"38": "play_noise_clap", "42": "play_clave1"}})
    assert _patch({"drum_keys": {"38": "play_noise_clap"}}, base)["drum_keys"] == {
        "38": "play_noise_clap"
    }
    assert _patch({"drum_keys": {}}, base)["drum_keys"] == {}


def test_family_caps_are_replaced_wholesale_for_the_same_reason():
    base = _patch({"tuning": {"family_caps": {"ins_violin": 800, "ins_flute": 400}}})
    doc = _patch({"tuning": {"family_caps": {"ins_violin": 800}}}, base)
    assert doc["tuning"]["family_caps"] == {"ins_violin": 800}
    # The rest of `tuning` still merges per lever around it.
    assert doc["tuning"]["max_speakers"] == 32


def test_a_patch_that_spells_a_channel_as_a_number_still_finds_it():
    """The file spells channels as strings because JSON has no integer keys,
    and Python callers reach for the number. Keying the two differently would
    add a second entry for the same channel and skip the merge entirely."""
    base = _patch({"channels": {"0": {"family": "ins_marimba"}}})
    doc = settings.merge(base, {"channels": {0: {"muted": True}}})
    assert doc["channels"] == {"0": {"family": "ins_marimba", "muted": True, "soloed": False}}


def test_merge_leaves_the_document_it_was_given_alone():
    """The session applies a patch to its current document and keeps the result
    only if validation passed. A merge that edited in place would leave the
    session holding a half-applied document after a refusal."""
    base = _patch({"channels": {"0": {"family": "ins_marimba"}}})
    with pytest.raises(settings.SettingsError):
        settings.merge(base, {"channels": {"0": {"family": "ins_noise"}}})
    assert base["channels"]["0"]["family"] == "ins_marimba"


def test_validate_does_not_edit_the_document_it_was_given():
    doc = {"version": settings.SETTINGS_VERSION, "channels": {0: {"family": "ins_tri"}}}
    settings.validate(doc)
    assert doc["channels"] == {0: {"family": "ins_tri"}}


def test_a_hand_edit_that_deletes_a_line_reads_as_not_setting_it():
    """Absence is not this file's failure mode -- a wrong value is. Someone
    deleting a line they did not want means "I am not setting this", and
    refusing the whole document over it would lose the other forty."""
    doc = settings.validate({"version": settings.SETTINGS_VERSION, "tuning": {"max_speakers": 8}})
    assert doc["tuning"]["max_speakers"] == 8
    assert doc["tuning"]["release_s"] == 0.1
    assert doc["channels"] == {}
    assert doc["drums"] == "auto"


def test_an_integer_channel_key_becomes_the_string_json_will_write():
    """A document built in Python and the same document read back from its own
    file have to be equal, or the session compares them and sees a change
    nobody made."""
    doc = settings.validate({**settings.defaults(), "channels": {0: {"family": "ins_tri"}}})
    assert doc["channels"] == {"0": {"family": "ins_tri", "muted": False, "soloed": False}}


# ---- what the compiler is handed ----


def test_channel_keys_become_integers_because_that_is_what_the_parser_compares():
    """`parse_notes` tests `msg.channel in channel_mutes` against a mido
    integer. A string key never matches, and the mute silently does nothing."""
    doc = _patch({"channels": {"0": {"family": "ins_tri"}, "9": {"muted": True}}})
    kwargs = settings.to_compile_kwargs(doc)
    assert kwargs["channel_families"] == {0: "ins_tri"}
    assert kwargs["channel_mutes"] == {9}
    assert isinstance(kwargs["channel_mutes"], set)


def test_multiple_soloed_channels_are_forwarded_as_integer_keys():
    doc = _patch({"channels": {"0": {"soloed": True}, "2": {"soloed": True}}})
    solos = settings.to_compile_kwargs(doc)["channel_solos"]
    assert solos == {0, 2}
    assert isinstance(solos, set)


def test_a_muted_channel_with_an_instrument_appears_in_both():
    """Muting is not un-choosing. The family is still what the row shows, and
    still what the compile uses the moment the mute comes off."""
    kwargs = settings.to_compile_kwargs(
        _patch({"channels": {"2": {"family": "ins_flute", "muted": True}}})
    )
    assert kwargs["channel_families"] == {2: "ins_flute"}
    assert kwargs["channel_mutes"] == {2}


def test_exact_channel_sounds_reach_the_compiler_with_integer_channel_keys():
    sound = palette.sounds_in_category("ins_noise")[0]
    kwargs = settings.to_compile_kwargs(
        _patch({"channels": {"9": {"sound": sound, "muted": True}}})
    )
    assert kwargs["channel_sounds"] == {9: sound}
    assert kwargs["channel_families"] == {}
    assert kwargs["channel_mutes"] == {9}


@pytest.mark.parametrize("mode,expected", [("auto", "auto"), ("on", True), ("off", False)])
def test_the_drum_mode_becomes_what_the_compiler_switches_on(mode, expected):
    assert settings.to_compile_kwargs(_patch({"drums": mode}))["drums"] is expected


def test_drum_keys_become_integer_keys_too():
    kwargs = settings.to_compile_kwargs(_patch({"drum_keys": {"38": "play_noise_clap"}}))
    assert kwargs["drum_key_overrides"] == {38: "play_noise_clap"}


def test_decaying_families_arrive_as_a_set_and_caps_as_milliseconds():
    doc = _patch(
        {"tuning": {"decaying_families": ["ins_violin"], "family_caps": {"ins_flute": 400}}}
    )
    kwargs = settings.to_compile_kwargs(doc)
    assert kwargs["decaying_families"] == {"ins_violin"}
    assert isinstance(kwargs["decaying_families"], set)
    assert kwargs["family_caps"] == {"ins_flute": 400}


def test_the_kwargs_are_only_ones_the_compiler_takes():
    """They are splatted into the call, so a key the compiler does not have is
    a TypeError at export time -- after the window has said it is working."""
    accepted = set(inspect.signature(compile_to_rawmap).parameters)
    assert set(settings.to_compile_kwargs(settings.defaults())) <= accepted


def test_the_song_and_the_output_folder_are_not_compiler_arguments():
    """`compile_to_rawmap` is bytes-out and takes the MIDI path positionally.
    Where the result is written is the caller's business."""
    kwargs = settings.to_compile_kwargs(settings.defaults(TINY_MIDI))
    assert "midi" not in kwargs
    assert "out_dir" not in kwargs
    assert "baseline" not in kwargs


# ---- the contract ----


def test_the_default_document_compiles_exactly_what_no_arguments_compile():
    """The whole point of the defaults, in bytes.

    If this fails, one default is wrong -- and the symptom in the field is that
    a map exported from the window differs from the same song compiled on the
    command line, for a lever nobody touched.
    """
    kwargs = settings.to_compile_kwargs(settings.defaults(TINY_MIDI))
    assert compile_to_rawmap(TINY_MIDI, **kwargs)[0] == compile_to_rawmap(TINY_MIDI)[0]


def test_the_document_actually_reaches_the_compile():
    """The byte gate above passes just as well if every keyword is inert. This
    is the other half: a setting that is set has to change the output."""
    kwargs = settings.to_compile_kwargs(_patch({"channels": {"0": {"muted": True}}}))
    _, muted = compile_to_rawmap(TINY_MIDI, **kwargs)
    _, plain = compile_to_rawmap(TINY_MIDI)
    assert muted["notes"] < plain["notes"]
