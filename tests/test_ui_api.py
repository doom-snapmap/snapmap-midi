"""The Javascript bridge, exercised with no browser engine anywhere near it.

Three claims, and every test here is one of them.

The first is that the bridge answers. pywebview resolves each call as a
promise, and an exception raised on the Python side arrives in Javascript as an
opaque Error with nothing worth showing someone who is looking at a window
rather than a console. So a missing file, a hand-written family that does not
exist, and a patch that is not a mapping at all are all payloads here rather
than tracebacks.

The second is that the answers are batched the way the first frame needs them.
`startup` carries settings, analysis, catalog, rulers and statistics together;
anything that can change the analysis carries the analysis back, because a
window told only about settings would go on drawing the last song's drum keys.

The third is the sidecar, which is the only reason a choice made in the window
outlives the window. Export writes it beside the song, opening the song again
applies it, and a sidecar that has been hand-edited into nonsense costs its
settings and not the song.

Nothing in this file imports pywebview and nothing skips without it. The file
dialogs answer before they reach `import webview`, and the two tests that need
a real dialog install a stand-in through `sys.modules` -- the same trick
`tests/test_cli.py` uses to prove the opposite branch.

Every test that exports names its own output folder under `tmp_path` and
compiles a COPY of the fixture. Export writes two files, `rawmap.json` into the
output folder and the settings sidecar beside the song, and a test that let
either of those default would write into the loader's own folder -- destroying
whatever map the person running the suite had loaded -- or leave a settings
file behind in `tests/fixtures/`.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

from snapmap_midi import paths
from snapmap_midi import settings as settings_module
from snapmap_midi.compile import compile_to_rawmap
from snapmap_midi.music.gm import DRUM_MAP
from snapmap_midi.sound import palette
from snapmap_midi.ui.api import Bridge

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_MIDI = str(FIXTURES / "tiny.mid")
WEB = Path(__file__).resolve().parents[1] / "src" / "snapmap_midi" / "ui" / "web"


def _song(tmp_path, name="song.mid") -> str:
    """A copy of the fixture, somewhere a sidecar may be written beside it."""
    path = tmp_path / name
    shutil.copyfile(TINY_MIDI, path)
    return str(path)


def _bridge(tmp_path, name="song.mid") -> Bridge:
    """A bridge on a copied song, with an output folder of its own."""
    bridge = Bridge(midi=_song(tmp_path, name))
    assert bridge.apply_settings({"out_dir": str(tmp_path / "out")})["ok"] is True
    return bridge


def _channel(payload, number) -> dict:
    return [c for c in payload["analysis"]["channels"] if c["channel"] == number][0]


class _FakeWebview:
    """Stands in for the pywebview module, which is not installed off Windows."""

    class FileDialog:
        OPEN = 10
        FOLDER = 20


class _FakeWindow:
    """A window whose file dialog answers with whatever the test wants."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def create_file_dialog(self, kind, **kwargs):
        self.calls.append((kind, kwargs))
        return self.answer


# ---- every method answers ----


def test_the_bridge_offers_every_method_the_window_calls():
    """`app.js` is written against these names and cannot be told it is wrong:
    a call to a method that is not here rejects its promise, and the window
    shows a toast about an Error instead of doing the thing."""
    called = set(re.findall(r"api\(\)\.([a-z_]+)\(", (WEB / "app.js").read_text(encoding="utf-8")))
    assert called, "app.js reaches the bridge some other way now"
    for name in sorted(called):
        assert callable(getattr(Bridge, name, None)), name


@pytest.mark.parametrize(
    "call",
    [
        lambda b: b.startup(),
        lambda b: b.catalog(),
        lambda b: b.get_settings(),
        lambda b: b.load_midi(TINY_MIDI),
        lambda b: b.apply_settings({"drums": "off"}),
        lambda b: b.dry_run(),
        lambda b: b.export(),
    ],
    ids=["startup", "catalog", "get_settings", "load_midi", "apply_settings", "dry_run", "export"],
)
def test_a_broken_session_is_an_answer_and_not_a_rejected_promise(call):
    """The catch has to be `Exception` rather than the errors this module knows
    about. Whatever goes wrong below it reaches Javascript as an Error carrying
    nothing, and the window can only report that something failed."""
    bridge = Bridge()
    bridge._session = None
    result = call(bridge)
    assert result["ok"] is False
    assert result["error"]


def test_a_patch_that_is_not_a_mapping_is_an_answer_not_a_crash():
    result = Bridge(midi=TINY_MIDI).apply_settings("nonsense")
    assert result["ok"] is False
    assert "nonsense" in result["error"]


# ---- opening ----


def test_startup_answers_in_one_call():
    """Four promises resolving in four orders paint an empty table, then a
    table with no dropdowns, then dropdowns with no ranges. Batching is what
    makes the first frame correct rather than what makes it quick."""
    payload = Bridge(midi=TINY_MIDI).startup()
    assert payload["ok"] is True
    assert set(payload) >= {
        "ok",
        "settings",
        "analysis",
        "catalog",
        "rulers",
        "stats",
        "audio",
        "window",
    }
    assert [c["channel"] for c in payload["analysis"]["channels"]] == [0, 1, 9]
    assert payload["rulers"]["9"] is None
    assert payload["stats"]["notes"]


def test_startup_with_no_song_says_so_without_failing():
    """The window opens on nothing at all when the command line named nothing.
    `stats` is null rather than absent or zeroed: no song and a song that
    compiles to nothing are different states and the window says different
    things about them."""
    payload = Bridge().startup()
    assert payload["ok"] is True
    assert payload["analysis"] is None
    assert payload["stats"] is None
    assert payload["rulers"] == {}
    assert payload["catalog"]["families"]


def test_startup_reports_audio_without_extracting_it(monkeypatch):
    """Opening the editor may inspect the cache and must never build it.

    Extraction takes tens of seconds and writes hundreds of megabytes. It is a
    button, not a side effect of asking for the first frame.
    """
    from snapmap_midi.audio import library

    state = {
        "ready": False,
        "count": 12,
        "expected": 890,
        "install": "D:/Steam/DOOM",
        "cache_dir": "C:/cache",
    }
    monkeypatch.setattr(library, "status", lambda: dict(state))
    monkeypatch.setattr(
        library,
        "extract",
        lambda: pytest.fail("startup extracted audio without an explicit request"),
    )
    assert Bridge().startup()["audio"] == state


def test_audio_status_failure_does_not_take_down_the_editor(monkeypatch):
    from snapmap_midi.audio import library

    def broken():
        raise OSError("cache cannot be read")

    monkeypatch.setattr(library, "status", broken)
    payload = Bridge().startup()
    assert payload["ok"] is True
    assert payload["audio"]["ready"] is False
    assert payload["audio"]["error"] == "cache cannot be read"


def test_opening_on_a_bad_path_still_opens(tmp_path):
    """`snapmap-midi ui missing.mid` must give a usable window that says what
    went wrong. A GUI user has no console to read a traceback in, so the
    constructor cannot raise and the first call cannot answer `ok: False` --
    that would leave the Open button in a window reporting failure."""
    bridge = Bridge(midi=str(tmp_path / "nope.mid"))
    payload = bridge.startup()
    assert payload["ok"] is True
    assert "nope.mid" in payload["error"]
    assert payload["analysis"] is None


def test_opening_a_song_after_a_bad_path_stops_reporting_the_bad_path(tmp_path):
    """The window asks for the whole payload again whenever the drums switch
    moves. A constructor complaint that outlived the file it was about would
    toast that dead path over and over for the rest of the session."""
    bridge = Bridge(midi=str(tmp_path / "nope.mid"))
    assert bridge.load_midi(TINY_MIDI)["ok"] is True
    assert "error" not in bridge.startup()


def test_loading_a_song_returns_the_analysis_the_settings_and_the_rulers():
    payload = Bridge().load_midi(TINY_MIDI)
    assert payload["ok"] is True
    assert payload["settings"]["midi"] == TINY_MIDI
    assert _channel(payload, 9)["is_drums"] is True
    assert payload["rulers"]["0"]["cells"][0]["note"] == 60


def test_a_song_that_is_not_there_is_an_answer_that_names_it(tmp_path):
    result = Bridge().load_midi(tmp_path / "nope.mid")
    assert result["ok"] is False
    assert "nope.mid" in result["error"]


def test_a_file_that_is_not_a_midi_file_is_an_answer_too(tmp_path):
    """The picker filters by extension and a person can still choose anything.
    mido raises something of its own here, which is why the guard is broad."""
    impostor = tmp_path / "notes.mid"
    impostor.write_text("this is not a MIDI file", encoding="utf-8")
    result = Bridge().load_midi(str(impostor))
    assert result["ok"] is False
    assert result["error"]


def test_a_failed_load_leaves_the_song_that_was_open_still_open(tmp_path):
    bridge = Bridge(midi=TINY_MIDI)
    assert bridge.load_midi(tmp_path / "nope.mid")["ok"] is False
    assert bridge.startup()["analysis"]["path"] == TINY_MIDI


def test_constructing_with_a_settings_file_has_already_applied_it(tmp_path):
    doc = settings_module.merge(
        settings_module.defaults(TINY_MIDI), {"channels": {"1": {"family": "ins_sine"}}}
    )
    path = tmp_path / "s.json"
    settings_module.save(doc, path)
    payload = Bridge(settings_path=str(path)).startup()
    assert payload["settings"]["channels"]["1"]["family"] == "ins_sine"
    assert payload["analysis"]["path"] == TINY_MIDI


# ---- the catalog ----


def test_the_catalog_offers_only_families_that_can_play_a_pitch():
    """`ins_string` is named like an instrument, sits in SUSTAINED beside the
    violins, and holds twelve unpitched effect samples. Offering it would
    compile the part to silence with no error anywhere."""
    families = Bridge().catalog()["families"]
    names = [f["name"] for f in families]
    assert names == palette.pitched_families()
    assert "ins_string" not in names
    assert "ins_noise" not in names
    assert "ins_brass_bells" in names


def test_every_family_in_the_catalog_carries_the_range_the_ruler_draws():
    """The window draws the hatched track from these two numbers and hard-codes
    no family of its own, so a family with no range would render as a track at
    note 0 and an instrument that reaches nothing."""
    index = palette.build_note_index()
    for family in Bridge().catalog()["families"]:
        assert (family["lowest"], family["highest"]) == palette.family_range(family["name"], index)


def test_the_workstation_catalog_contains_the_entire_shipped_sound_palette():
    catalog = Bridge().catalog()
    assert [group["name"] for group in catalog["sound_groups"]] == palette.categories()
    offered = [sound["name"] for group in catalog["sound_groups"] for sound in group["sounds"]]
    assert offered == palette.all_sounds()
    assert catalog["sound_count"] == len(offered) == 890


def test_sound_groups_mark_which_categories_can_follow_midi_pitch():
    catalog = Bridge().catalog()
    pitched = {group["name"] for group in catalog["sound_groups"] if group["pitched"]}
    assert pitched == set(palette.pitched_families())


def test_the_catalog_names_the_drum_sounds_and_what_they_sound_like():
    """The names lie: `play_noise_crash` is a shaker and `play_noise_tom` is a
    knock on a wooden door. A picker showing only names sends people to the tom
    for a tom, which is what the ear-labels are for."""
    sounds = Bridge().catalog()["drum_sounds"]
    assert [s["name"] for s in sounds] == palette.drum_sound_pool()
    by_name = {s["name"]: s for s in sounds}
    assert by_name["play_noise_hat"]["category"] == "ins_noise"
    assert "hi-hat" in by_name["play_noise_hat"]["label"]
    assert by_name["play_noise_hat"]["label"].startswith("play_noise_hat")


def test_a_sound_label_is_one_line_and_not_the_record_it_is_stored_as():
    """`sound_labels()` is nested by category and each label is a record --
    `{heard, role, confirmed}`. Handed over as it is stored, the window would
    put `[object Object]` in every row it has a label for."""
    for sound in Bridge().catalog()["drum_sounds"]:
        assert isinstance(sound["label"], str)
        assert sound["label"]


def test_every_sound_the_drum_table_already_uses_can_be_chosen_again():
    """Otherwise there is no way back to the default after trying something
    else, short of hand-editing the settings file."""
    offered = {s["name"] for s in Bridge().catalog()["drum_sounds"]}
    assert set(DRUM_MAP.values()) <= offered


def test_the_catalog_names_only_the_drum_keys_the_open_song_plays():
    """All 128 would be a picker whose rows are mostly keys the file never
    touches, and the file's own keys are the ones the Drums tab is for."""
    catalog = Bridge(midi=TINY_MIDI).catalog()
    analysis = Bridge(midi=TINY_MIDI).startup()["analysis"]
    kit = [c for c in analysis["channels"] if c["is_drums"]][0]
    assert set(catalog["drum_names"]) == set(kit["drum_keys"])
    assert catalog["drum_names"]["36"] == "Bass Drum 1"


def test_opening_a_song_carries_a_fresh_catalog_with_it():
    """`drum_names` covers the loaded file's keys and nothing else, so it is
    stale the moment another file opens. A window that had to ask for it
    separately would draw one frame of the new song with the old song's keys."""
    bridge = Bridge()
    assert bridge.catalog()["drum_names"] == {}
    payload = bridge.load_midi(TINY_MIDI)
    assert payload["catalog"]["drum_names"]
    assert payload["catalog"]["families"] == bridge.catalog()["families"]


# ---- local audio preview ----


def test_a_cached_sound_crosses_the_bridge_as_a_playable_data_uri(monkeypatch):
    from snapmap_midi.audio import library

    monkeypatch.setattr(library, "expected_names", lambda: ["play_one"])
    monkeypatch.setattr(library, "read_wav", lambda name: b"RIFF" if name == "play_one" else None)
    assert Bridge().preview_sound("play_one") == {
        "ok": True,
        "sound": "play_one",
        "data_uri": "data:audio/wav;base64,UklGRg==",
    }


def test_a_sound_outside_the_palette_is_refused_before_the_cache_is_read(monkeypatch):
    from snapmap_midi.audio import library

    monkeypatch.setattr(library, "expected_names", lambda: ["play_one"])
    monkeypatch.setattr(
        library,
        "read_wav",
        lambda name: pytest.fail("an unknown palette name reached the cache"),
    )
    result = Bridge().preview_sound("../elsewhere")
    assert result["ok"] is False
    assert "shipped palette" in result["error"]


def test_an_unextracted_sound_explains_the_one_step_that_is_missing(monkeypatch):
    from snapmap_midi.audio import library

    monkeypatch.setattr(library, "expected_names", lambda: ["play_one"])
    monkeypatch.setattr(library, "read_wav", lambda name: None)
    result = Bridge().preview_sound("play_one")
    assert result["ok"] is False
    assert "set up audio preview" in result["error"]


def test_a_channel_preview_resolves_the_same_sound_as_the_compiler(monkeypatch):
    from snapmap_midi.audio import library

    family = "ins_piano"
    note = 60
    expected = palette.decl_for(family, note, palette.build_note_index())
    assert expected is not None
    monkeypatch.setattr(library, "expected_names", lambda: [expected])
    monkeypatch.setattr(library, "read_wav", lambda name: b"RIFF")
    result = Bridge().preview_note(family, note)
    assert result["ok"] is True
    assert result["sound"] == expected


@pytest.mark.parametrize("note", [-1, 128, 60.5, True, "not-a-note"])
def test_a_preview_note_has_to_be_a_midi_note(note):
    result = Bridge().preview_note("ins_piano", note)
    assert result["ok"] is False
    assert result["error"]


def test_audio_extraction_is_the_explicit_bridge_call(monkeypatch):
    from snapmap_midi.audio import library

    state = {
        "ready": True,
        "count": 2,
        "expected": 2,
        "install": "D:/DOOM",
        "cache_dir": "C:/cache",
        "written": 2,
        "skipped": 0,
        "failed": [],
    }
    calls = []

    def extract():
        calls.append(True)
        return dict(state)

    monkeypatch.setattr(library, "extract", extract)
    assert Bridge().extract_audio() == {"ok": True, "audio": state}
    assert calls == [True]


def test_an_incomplete_extraction_names_failure_without_breaking_the_bridge(monkeypatch):
    from snapmap_midi.audio import library

    state = {
        "ready": False,
        "count": 1,
        "expected": 2,
        "install": "D:/DOOM",
        "cache_dir": "C:/cache",
        "written": 1,
        "skipped": 0,
        "failed": ["play_two"],
    }
    monkeypatch.setattr(library, "extract", lambda: dict(state))
    result = Bridge().extract_audio()
    assert result["ok"] is False
    assert result["audio"] == state
    assert "1 sound could" in result["error"]


def test_preview_manifest_crosses_the_bridge_as_one_global_song():
    result = Bridge(midi=TINY_MIDI).preview_manifest()
    assert result["ok"] is True
    assert result["preview"]["events"]
    assert result["preview"]["duration_ms"] > 0
    assert result["preview"]["timing"]["ticks_per_beat"] == 480


def test_global_preview_fetches_only_the_samples_the_current_song_uses(monkeypatch):
    from snapmap_midi.audio import library

    bridge = Bridge(midi=TINY_MIDI)
    used = bridge.preview_manifest()["preview"]["sounds"]
    requested = used[:2]
    reads = []

    def read_wav(name):
        reads.append(name)
        return b"RIFF"

    monkeypatch.setattr(library, "read_wav", read_wav)
    result = bridge.preview_samples(requested + requested[:1])
    assert result["ok"] is True
    assert list(result["samples"]) == requested
    assert set(result["samples"].values()) == {"data:audio/wav;base64,UklGRg=="}
    assert reads == requested
    assert result["missing"] == []


def test_global_preview_refuses_a_palette_sound_the_current_song_does_not_use(monkeypatch):
    from snapmap_midi.audio import library

    bridge = Bridge(midi=TINY_MIDI)
    used = set(bridge.preview_manifest()["preview"]["sounds"])
    outside = next(sound for sound in palette.all_sounds() if sound not in used)
    monkeypatch.setattr(
        library,
        "read_wav",
        lambda name: pytest.fail("an out-of-song sound reached the audio cache"),
    )
    result = bridge.preview_samples([outside])
    assert result["ok"] is False
    assert "not used by the current converted song" in result["error"]


def test_global_preview_reports_missing_used_samples_without_failing_the_bridge(monkeypatch):
    from snapmap_midi.audio import library

    bridge = Bridge(midi=TINY_MIDI)
    used = bridge.preview_manifest()["preview"]["sounds"][:2]
    monkeypatch.setattr(library, "read_wav", lambda name: None)
    assert bridge.preview_samples(used) == {"ok": True, "samples": {}, "missing": used}


# ---- settings ----


def test_settings_apply_as_a_patch_and_answer_with_the_whole_document():
    bridge = Bridge(midi=TINY_MIDI)
    bridge.apply_settings({"channels": {"0": {"family": "ins_marimba"}}})
    payload = bridge.apply_settings({"channels": {"0": {"muted": True}}})
    assert payload["ok"] is True
    assert payload["settings"]["channels"]["0"] == {"family": "ins_marimba", "muted": True}
    assert bridge.get_settings()["settings"] == payload["settings"]


def test_restore_conversion_defaults_keeps_the_song_and_track_assignments():
    bridge = Bridge(midi=TINY_MIDI)
    sound = palette.sounds_in_category("ins_noise")[0]
    bridge.apply_settings(
        {
            "channels": {"0": {"sound": sound}},
            "tuning": {"max_speakers": 4, "hard_stop": True},
        }
    )
    result = bridge.reset_tuning()
    assert result["ok"] is True
    assert result["settings"]["midi"] == TINY_MIDI
    assert result["settings"]["channels"]["0"]["sound"] == sound
    assert result["settings"]["tuning"] == settings_module.defaults()["tuning"]


def test_a_family_that_cannot_play_a_pitch_is_refused_and_changes_nothing():
    bridge = Bridge(midi=TINY_MIDI)
    before = bridge.get_settings()["settings"]
    result = bridge.apply_settings({"channels": {"0": {"family": "ins_string"}}})
    assert result["ok"] is False
    assert "ins_string" in result["error"]
    assert bridge.get_settings()["settings"] == before


def test_applying_answers_with_fresh_statistics():
    bridge = Bridge(midi=TINY_MIDI)
    before = bridge.startup()["stats"]["notes"]
    payload = bridge.apply_settings({"channels": {"0": {"muted": True}}})
    assert payload["stats"]["notes"] < before


def test_applying_answers_with_the_analysis_and_the_rulers_as_well():
    """A drums change rewrites `is_drums` and the whole drum-key list, and
    neither is in the settings document. Without them in this answer the window
    has to call `startup` again after every drums change, and until it returns
    the Drums tab lists keys for a channel the compiler has stopped routing
    through `DRUM_MAP`."""
    payload = Bridge(midi=TINY_MIDI).apply_settings({"drums": "off"})
    assert payload["ok"] is True
    assert _channel(payload, 9)["is_drums"] is False
    assert _channel(payload, 9)["drum_keys"] == {}
    assert payload["rulers"]["9"] is not None


# ---- compiling ----


def test_a_dry_run_is_a_real_compile_and_writes_nothing(tmp_path):
    """An estimate that disagreed with the export would be discovered in game,
    and closing that loop is the entire reason the window exists."""
    out = tmp_path / "out"
    bridge = Bridge(midi=TINY_MIDI)
    bridge.apply_settings({"channels": {"1": {"family": "ins_marimba"}}, "out_dir": str(out)})
    expected = compile_to_rawmap(
        TINY_MIDI, **settings_module.to_compile_kwargs(bridge.get_settings()["settings"])
    )[1]
    report = bridge.dry_run()
    assert report["ok"] is True
    assert {k: v for k, v in report["stats"].items() if k != "warnings"} == expected
    assert not out.exists()


def test_a_dry_run_before_a_song_is_open_says_so():
    result = Bridge().dry_run()
    assert result["ok"] is False
    assert "song" in result["error"]


def test_muting_every_channel_warns_that_nothing_will_play():
    bridge = Bridge(midi=TINY_MIDI)
    payload = bridge.apply_settings({"channels": {str(c): {"muted": True} for c in (0, 1, 9)}})
    assert payload["stats"]["warnings"][0] == "Nothing will play: all 3 channels are muted."


def test_export_writes_the_map_and_reports_where_it_went(tmp_path):
    bridge = _bridge(tmp_path)
    result = bridge.export()
    assert result["ok"] is True
    destination = Path(result["destination"])
    assert destination == (tmp_path / "out" / paths.RAWMAP_NAME).resolve()
    assert destination.read_bytes()
    assert result["replaced"] is False
    assert result["advice"]
    assert result["stats"]["notes"]
    assert bridge.export()["replaced"] is True


def test_export_before_a_song_is_open_says_so_and_writes_nothing(tmp_path):
    bridge = Bridge()
    bridge.apply_settings({"out_dir": str(tmp_path / "out")})
    assert bridge.export()["ok"] is False
    assert not (tmp_path / "out").exists()


# ---- the sidecar ----


def test_export_writes_the_settings_sidecar_beside_the_song(tmp_path):
    """The map is one deliverable and the choices behind it are the other. Until
    this landed, closing the window lost every choice in it -- `sidecar_path`
    and `save` existed with nothing in the product calling either."""
    bridge = _bridge(tmp_path)
    bridge.apply_settings({"channels": {"0": {"family": "ins_marimba"}}})
    result = bridge.export()

    sidecar = Path(result["sidecar"])
    assert sidecar == settings_module.sidecar_path(tmp_path / "song.mid")
    assert settings_module.load(sidecar)["channels"]["0"]["family"] == "ins_marimba"


def test_reopening_a_song_restores_the_choices_it_was_exported_with(tmp_path):
    """The point of writing it. A second session on the same song opens on the
    afternoon's tuning rather than on the compiler's guesses."""
    first = _bridge(tmp_path)
    first.apply_settings(
        {"channels": {"0": {"family": "ins_marimba"}}, "tuning": {"max_speakers": 8}}
    )
    first.export()

    payload = Bridge().load_midi(tmp_path / "song.mid")
    assert payload["ok"] is True
    assert "sidecar_error" not in payload
    assert payload["settings"]["channels"]["0"]["family"] == "ins_marimba"
    assert payload["settings"]["tuning"]["max_speakers"] == 8


def test_the_sidecar_is_applied_after_the_load_and_not_before(tmp_path):
    """`load` clears `channels` and `drum_keys` on purpose, because the last
    song's instruments must not follow the user into this one. A sidecar
    applied first would be erased by the very load it was meant to configure,
    and the window would open on the defaults with the file sitting there."""
    song = _song(tmp_path)
    doc = settings_module.merge(
        settings_module.defaults(song),
        {"channels": {"1": {"family": "ins_sine"}}, "drum_keys": {"36": "play_clave1"}},
    )
    settings_module.save(doc, settings_module.sidecar_path(song))

    bridge = Bridge(midi=TINY_MIDI)
    bridge.apply_settings({"channels": {"0": {"family": "ins_marimba"}}})
    payload = bridge.load_midi(song)
    assert payload["settings"]["channels"] == {"1": {"family": "ins_sine", "muted": False}}
    assert payload["settings"]["drum_keys"] == {"36": "play_clave1"}


def test_a_sidecar_remembers_settings_and_not_which_file_they_were_for(tmp_path):
    """The path in the document was written by an earlier session and the file
    has just been copied, renamed, or handed to somebody else. Honouring it
    would point the session at a song nobody asked to open."""
    song = _song(tmp_path, name="renamed.mid")
    doc = settings_module.merge(
        settings_module.defaults("D:/somewhere/else.mid"),
        {"channels": {"1": {"family": "ins_sine"}}},
    )
    settings_module.save(doc, settings_module.sidecar_path(song))

    payload = Bridge().load_midi(song)
    assert payload["settings"]["midi"] == song
    assert payload["settings"]["channels"]["1"]["family"] == "ins_sine"


def test_a_corrupt_sidecar_costs_its_settings_and_not_the_song(tmp_path):
    """This file is meant to be hand-edited, so a broken one is an ordinary
    event. Refusing to open the song over it would make the window unusable for
    exactly the person who was trying to fix the file."""
    song = _song(tmp_path)
    settings_module.sidecar_path(song).write_text("{not json", encoding="utf-8")

    payload = Bridge().load_midi(song)
    assert payload["ok"] is True
    assert payload["analysis"]["path"] == song
    assert "sidecar_error" in payload
    assert "song.mid.snapmap.json" in payload["sidecar_error"]


def test_a_sidecar_naming_a_family_that_does_not_exist_is_reported_not_obeyed(tmp_path):
    """A hand edit fails validation rather than JSON parsing, and the two have
    to end up in the same place: the song opens, the settings do not."""
    song = _song(tmp_path)
    settings_module.sidecar_path(song).write_text(
        json.dumps({"version": 1, "channels": {"0": {"family": "ins_string"}}}), encoding="utf-8"
    )
    payload = Bridge().load_midi(song)
    assert payload["ok"] is True
    assert payload["settings"]["channels"] == {}
    assert "ins_string" in payload["sidecar_error"]


def test_a_sidecar_that_cannot_be_written_does_not_fail_the_export(tmp_path):
    """The map is the deliverable and the sidecar is a convenience. A read-only
    folder, a name already taken by a directory, a song on a share that has
    gone away -- none of them are a reason to tell someone their map failed
    when it is sitting on disk."""
    bridge = _bridge(tmp_path)
    settings_module.sidecar_path(tmp_path / "song.mid").mkdir()

    result = bridge.export()
    assert result["ok"] is True
    assert Path(result["destination"]).read_bytes()
    assert result["sidecar"] is None
    assert result["sidecar_error"]


# ---- the file dialogs ----


def test_the_dialogs_answer_when_no_window_is_attached():
    """Every method of this object exists before the window does: the window is
    created WITH the bridge as its Javascript surface, so there is a moment
    where one exists and the other does not."""
    bridge = Bridge(midi=TINY_MIDI)
    for call in (bridge.pick_midi, bridge.pick_out_dir, bridge.pick_baseline):
        result = call()
        assert result["ok"] is False
        assert "webview" not in json.dumps(result), (
            "the dialog reached `import webview`, which is what makes this file "
            "unrunnable on a machine without pywebview"
        )


def test_attaching_the_window_is_what_gives_the_bridge_a_dialog_to_hang_on():
    window = _FakeWindow(None)
    bridge = Bridge()
    bridge.attach(window)
    assert bridge._window is window


def test_choosing_a_song_in_the_dialog_opens_it(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "webview", _FakeWebview())
    window = _FakeWindow((TINY_MIDI,))
    bridge = Bridge()
    bridge.attach(window)

    payload = bridge.pick_midi()
    assert payload["ok"] is True
    assert payload["analysis"]["path"] == TINY_MIDI
    assert payload["catalog"]["drum_names"]
    assert window.calls[0][0] == _FakeWebview.FileDialog.OPEN


def test_cancelling_a_dialog_changes_nothing(monkeypatch):
    """Cancelling is not failing. The answer says the call did not happen rather
    than reporting an error the window would toast at somebody who had just
    decided not to do it."""
    monkeypatch.setitem(sys.modules, "webview", _FakeWebview())
    bridge = Bridge(midi=TINY_MIDI)
    bridge.attach(_FakeWindow(None))

    before = bridge.get_settings()["settings"]
    for call in (bridge.pick_midi, bridge.pick_out_dir, bridge.pick_baseline):
        result = call()
        assert result["ok"] is False
        assert "error" not in result
    assert bridge.get_settings()["settings"] == before


def test_choosing_an_output_folder_records_it(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "webview", _FakeWebview())
    window = _FakeWindow((str(tmp_path),))
    bridge = Bridge(midi=TINY_MIDI)
    bridge.attach(window)

    payload = bridge.pick_out_dir()
    assert payload["ok"] is True
    assert payload["settings"]["out_dir"] == str(tmp_path)
    assert window.calls[0][0] == _FakeWebview.FileDialog.FOLDER


def test_choosing_a_baseline_map_records_it(monkeypatch, tmp_path):
    """It exists so the baseline is not a path somebody types. A saved map lives
    wherever the game put it, and typing that path is how it gets typed wrong."""
    monkeypatch.setitem(sys.modules, "webview", _FakeWebview())
    saved = tmp_path / "saved.json"
    saved.write_text("{}", encoding="utf-8")
    bridge = Bridge(midi=TINY_MIDI)
    bridge.attach(_FakeWindow((str(saved),)))

    payload = bridge.pick_baseline()
    assert payload["ok"] is True
    assert payload["settings"]["baseline"] == str(saved)
