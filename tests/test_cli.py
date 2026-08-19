"""The command-line surface, and the output contract in particular.

The destination is the part of this tool a user is most likely to get wrong,
and it used to be impossible to get right by accident: `--out` accepted any
filename and the loader reads exactly one. These tests pin the contract that
replaced it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from snapmap_midi import cli as cli_module
from snapmap_midi import paths
from snapmap_midi import settings as settings_module
from snapmap_midi.cli import main
from snapmap_midi.rawmap.codec import deserialize

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_MIDI = str(FIXTURES / "tiny.mid")


def _record_compile(monkeypatch) -> dict:
    """Capture the keyword arguments the compiler is actually called with.

    Precedence between a settings file and a typed flag is invisible in the
    output: `max_speakers` 8 and 32 both produce a valid map, and the wrong one
    is only wrong to the person who set it. The call itself is the only place
    the answer exists.
    """
    from snapmap_midi.compile import compile_to_rawmap as real

    captured = {}

    def recording(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr("snapmap_midi.cli.compile_to_rawmap", recording)
    return captured


def _settings_file(tmp_path, patch) -> str:
    """A settings file on disk holding one deliberate change."""
    path = tmp_path / "s.json"
    settings_module.save(settings_module.merge(settings_module.defaults(), patch), path)
    return str(path)


def _stub_window(monkeypatch) -> list:
    """Stand in for the window, and record what it was asked to open.

    Patched on the module rather than on `snapmap_midi.cli`, because `_ui`
    imports the name at call time -- which is what keeps `snapmap-midi compile`
    working on a machine with no pywebview.
    """
    from snapmap_midi.ui import app

    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(app, "run", fake_run)
    monkeypatch.setattr(cli_module, "_has_display", lambda: True)
    return calls


def test_compile_needs_only_a_midi_file(tmp_path, capsys):
    """The headline of the CLI: one argument, no configuration."""
    assert main(["compile", TINY_MIDI, "--out-dir", str(tmp_path)]) == 0
    written = tmp_path / "rawmap.json"
    assert written.is_file()
    classes = [
        (e.get("entityDef") or {}).get("className")
        for e in deserialize(written.read_bytes())["entities"]
    ]
    assert "idTarget_Timeline" in classes
    assert "compiled" in capsys.readouterr().out


def test_the_filename_is_always_rawmap_json(tmp_path):
    """`--out-dir` moves the folder and never the name. The loader reads one
    filename, so a map called anything else is a file the user has to know to
    rename -- which is what the old `--out` produced."""
    nested = tmp_path / "some" / "deep" / "folder"
    assert main(["compile", TINY_MIDI, "--out-dir", str(nested)]) == 0
    assert [p.name for p in nested.iterdir()] == ["rawmap.json"]


def test_the_output_folder_is_created(tmp_path):
    """The loader makes this folder the first time it runs. Compiling on a
    machine where that has not happened must still work."""
    missing = tmp_path / "not-yet"
    assert not missing.exists()
    assert main(["compile", TINY_MIDI, "--out-dir", str(missing)]) == 0
    assert (missing / "rawmap.json").is_file()


def test_the_retired_out_flag_refuses_instead_of_guessing(tmp_path, capsys):
    """`--out` was removed, and removing it was not enough. argparse
    abbreviates unambiguous prefixes, so `--out song.json` bound to
    `--out-dir` and wrote `song.json/rawmap.json` -- a DIRECTORY named after
    the file someone meant to write, with no error. Anyone working from muscle
    memory or an old note got that silently."""
    with pytest.raises(SystemExit) as exit_info:
        main(["compile", TINY_MIDI, "--out", str(tmp_path / "song.json")])
    assert exit_info.value.code == 2
    assert "--out was removed" in capsys.readouterr().err
    assert not (tmp_path / "song.json").exists()


def test_no_flag_binds_by_abbreviation(tmp_path):
    """The same trap, for every other flag. `--but` bound to `--button`."""
    for abbreviated in ("--but", "--out-d", "--basel"):
        with pytest.raises(SystemExit):
            main(["compile", TINY_MIDI, abbreviated, "x", "--out-dir", str(tmp_path)])


def test_missing_midi_file_is_a_clean_error(tmp_path, capsys):
    """Not a traceback. Mistyping a path is the most ordinary mistake there
    is, and the MIDI reader's bare FileNotFoundError is not an answer."""
    assert main(["compile", str(tmp_path / "nope.mid"), "--out-dir", str(tmp_path)]) == 2
    assert "no such MIDI file" in capsys.readouterr().out
    assert not (tmp_path / "rawmap.json").exists()


def test_the_audition_command_is_gone(tmp_path):
    """Removed rather than kept as a hidden alias. Auditioning built a second
    kind of map whose switch played a category in sequence; the window answers
    the question that was actually being asked -- which family suits this
    channel -- and a command that still half-worked would send people back to
    guessing by ear one sound at a time."""
    with pytest.raises(SystemExit) as exit_info:
        main(["audition", "ins_noise", "--out-dir", str(tmp_path)])
    assert exit_info.value.code == 2
    assert not (tmp_path / "rawmap.json").exists()


def test_extract_builds_the_preview_cache_only_when_requested(monkeypatch, capsys):
    from snapmap_midi.audio import library

    calls = []

    def extract(**kwargs):
        calls.append(kwargs)
        kwargs["progress"](2, 2, "play_two")
        return {
            "ready": True,
            "cache_dir": "C:/cache",
            "written": 2,
            "skipped": 0,
            "count": 2,
            "expected": 2,
            "failed": [],
        }

    monkeypatch.setattr(library, "extract", extract)
    assert main(["extract", "--install", "D:/DOOM", "--force"]) == 0
    assert len(calls) == 1
    assert calls[0]["install"] == "D:/DOOM"
    assert calls[0]["force"] is True
    assert callable(calls[0]["progress"])
    out = capsys.readouterr().out
    assert "2 decoded" in out
    assert "C:/cache" in out


def test_extract_without_game_audio_is_a_clean_error(monkeypatch, capsys):
    from snapmap_midi.audio import library, wwise

    def unavailable(**kwargs):
        raise wwise.SoundsUnavailableError("no install found")

    monkeypatch.setattr(library, "extract", unavailable)
    assert main(["extract"]) == 2
    assert "no game audio" in capsys.readouterr().out


def test_extract_returns_one_when_any_palette_sound_is_still_missing(monkeypatch, capsys):
    from snapmap_midi.audio import library

    monkeypatch.setattr(
        library,
        "extract",
        lambda **kwargs: {
            "ready": False,
            "cache_dir": "C:/cache",
            "written": 1,
            "skipped": 0,
            "count": 1,
            "expected": 2,
            "failed": ["play_two"],
        },
    )
    assert main(["extract"]) == 1
    assert "play_two" in capsys.readouterr().out


def test_baseline_flag_adds_to_a_supplied_map(tmp_path, minimal_timeline_map):
    """The path that used to be mandatory still works, now as an option."""
    baseline = tmp_path / "level.json"
    baseline.write_text(json.dumps(minimal_timeline_map), encoding="utf-8")
    assert (
        main(["compile", TINY_MIDI, "--baseline", str(baseline), "--out-dir", str(tmp_path)]) == 0
    )
    obj = deserialize((tmp_path / "rawmap.json").read_bytes())
    # The supplied map's own timeline was reused as the master scheduler.
    # Pitch-controlled voices are auxiliary Timeline emitters, not additional
    # schedulers and not Speaker-class entities.
    timelines = [
        e
        for e in obj["entities"]
        if (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    ]
    masters = [
        entity
        for entity in timelines
        if (entity.get("entityDef") or {}).get("inherit") == "snapmaps/logic/timeline"
    ]
    emitters = [
        entity
        for entity in timelines
        if entity.get("displayName", "").startswith("snapmap-midi-v")
    ]
    assert len(masters) == 1 and masters[0]["uniqueId"] == 1
    # 2 voices: all four notes in TINY_MIDI are expressive one-shots (each
    # already carries its own pitch/volume adjustment, isolating it for that
    # reason alone), but they no longer all share identical scheduling.
    # Piano (channel 0) is one of the families `_AUTOMATIC_NOTE_OFF_OVERRIDES`
    # excludes from the automatic Note Off default, so it keeps its full,
    # uncapped natural decay while violin's (channel 1) is capped at its own
    # note-off -- different enough durations that they no longer fit
    # sequentially on one shared lane.
    assert len(emitters) == 2
    assert not any(
        (entity.get("entityDef") or {}).get("className")
        == "idSnapMapGameEntity_Speaker"
        for entity in obj["entities"]
    )
    assert timelines[0]["uniqueId"] == 1  # the id the fixture gave it


def test_silence_is_reported(tmp_path, capsys, monkeypatch):
    """A map that loads and plays nothing looks exactly like success until
    someone presses the switch."""
    import snapmap_midi.cli as cli

    monkeypatch.setattr(
        cli, "compile_to_rawmap", lambda *a, **k: (b"{}", {"notes": 0, "dropped": 0})
    )
    assert main(["compile", TINY_MIDI, "--out-dir", str(tmp_path)]) == 0
    assert "will be silent" in capsys.readouterr().out


@pytest.mark.parametrize("out_dir", [None, "explicit"])
def test_destination_resolution(tmp_path, out_dir, monkeypatch):
    """With no `--out-dir` the map goes to the loader's folder; with one it
    goes there. The filename never moves."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    if out_dir is None:
        assert paths.rawmap_destination() == tmp_path / "local" / "snapmap-plus" / "rawmap.json"
    else:
        assert paths.rawmap_destination(tmp_path / out_dir) == tmp_path / out_dir / "rawmap.json"


def test_destination_falls_back_when_there_is_no_local_appdata(tmp_path, monkeypatch):
    """The game is Windows-only, so off Windows there is no folder worth
    inventing. Write to the working directory and let the caller be told."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.loader_dir() is None
    assert paths.rawmap_destination() == Path(tmp_path).resolve() / "rawmap.json"


def test_the_fallback_is_not_reported_as_loadable(tmp_path, monkeypatch, capsys):
    """Writing to the working directory because there IS no loader folder is
    not the same as landing where the loader reads. Saying otherwise is the
    quiet wrong answer the old `--out` produced."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.destination_is_loadable(paths.rawmap_destination()) is False
    assert main(["compile", TINY_MIDI]) == 0
    out = capsys.readouterr().out
    assert "sh_rawmaps_on" not in out
    assert "copy it to the game machine" in out


def test_a_relative_out_dir_pointing_at_the_loader_is_recognised(tmp_path, monkeypatch, capsys):
    """`--out-dir .` from inside the loader's own folder puts the map exactly
    where it belongs. Comparing unresolved paths reported that as misplaced."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    loader = tmp_path / paths.LOADER_DIR_NAME
    loader.mkdir()
    monkeypatch.chdir(loader)
    assert main(["compile", TINY_MIDI, "--out-dir", "."]) == 0
    out = capsys.readouterr().out
    assert "sh_rawmaps_on" in out
    assert "move it there" not in out
    assert (loader / "rawmap.json").is_file()


def test_an_out_dir_elsewhere_is_reported_as_needing_a_move(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert main(["compile", TINY_MIDI, "--out-dir", str(tmp_path / "somewhere")]) == 0
    out = capsys.readouterr().out
    assert "move it there to play it" in out
    assert "sh_rawmaps_on" not in out


# ---- what a settings file decides, and what a flag takes back ----


def test_the_compilers_own_defaults_stand_when_nothing_else_speaks(tmp_path, monkeypatch):
    """The flags default to None now so that a file can fill them, which means
    the values they used to carry live somewhere else. If that move lost one,
    every compile with no file and no flag would quietly change."""
    captured = _record_compile(monkeypatch)
    assert main(["compile", TINY_MIDI, "--out-dir", str(tmp_path)]) == 0
    assert captured["button_name"] == "snapmap-midi-song"
    assert captured["drums"] == "auto"
    assert captured["max_speakers"] == 32
    assert captured["release_s"] == 0.1
    assert captured["hard_stop"] is False
    assert captured["max_events"] is None


def test_a_settings_file_lever_survives_when_no_flag_contradicts_it(tmp_path, monkeypatch):
    """The whole point of `--settings`. argparse always supplies a default, so
    filtering the file down to the keys nobody has a flag for meant
    `max_speakers: 8` in a file the user had deliberately loaded compiled at 32
    with nothing said anywhere -- the quiet wrong answer `_RetiredOut` exists to
    prevent, in the one feature whose purpose is replaying a session."""
    path = _settings_file(tmp_path, {"tuning": {"max_speakers": 8}})
    captured = _record_compile(monkeypatch)
    assert main(["compile", TINY_MIDI, "--settings", path, "--out-dir", str(tmp_path)]) == 0
    assert captured["max_speakers"] == 8


def test_a_flag_the_user_typed_beats_the_file(tmp_path, monkeypatch):
    """The other direction, and the reason the fix is an ordering rather than a
    swap: a file loaded once cannot be allowed to outrank the flag someone is
    typing right now."""
    path = _settings_file(tmp_path, {"tuning": {"max_speakers": 8}})
    captured = _record_compile(monkeypatch)
    argv = ["compile", TINY_MIDI, "--settings", path, "--max-speakers", "4"]
    assert main(argv + ["--out-dir", str(tmp_path)]) == 0
    assert captured["max_speakers"] == 4


def test_a_settings_file_can_turn_on_a_switch_no_flag_mentions(tmp_path, monkeypatch):
    """`--hard-stop` was `store_true`, so its absence and its refusal were the
    same value: False beat `hard_stop: true` in the file every time. A switch
    has to be able to say nothing, which is what `store_const` with a None
    default buys."""
    path = _settings_file(tmp_path, {"tuning": {"hard_stop": True}})
    captured = _record_compile(monkeypatch)
    assert main(["compile", TINY_MIDI, "--settings", path, "--out-dir", str(tmp_path)]) == 0
    assert captured["hard_stop"] is True


def test_a_button_named_like_a_drums_mode_is_still_a_name(tmp_path, monkeypatch):
    """`--drums` is three words on the command line and a tri-state in the
    compiler, so it needs translating. Translating every flag through that same
    table turns `--button off` into `button_name=False`, which reaches the
    document as a switch label nobody can find again."""
    captured = _record_compile(monkeypatch)
    argv = ["compile", TINY_MIDI, "--button", "off", "--out-dir", str(tmp_path)]
    assert main(argv) == 0
    assert captured["button_name"] == "off"


def test_the_channel_choices_in_a_settings_file_reach_the_compiler(tmp_path, monkeypatch):
    """A file written by the window carries per-channel instruments and mutes,
    which have no flag at all. If only the tuning levers came through, exporting
    from the window and replaying the file would produce different songs."""
    patch = {"channels": {"0": {"family": "ins_marimba", "muted": False}}}
    path = _settings_file(tmp_path, patch)
    captured = _record_compile(monkeypatch)
    assert main(["compile", TINY_MIDI, "--settings", path, "--out-dir", str(tmp_path)]) == 0
    assert captured["channel_families"] == {0: "ins_marimba"}


def test_a_settings_file_that_cannot_be_honoured_exits_2_naming_the_offender(tmp_path, capsys):
    """Hand editing is the ordinary way this file changes, so a bad one is an
    ordinary event and not a bug. A traceback would bury the one thing the
    person can act on -- the key they mistyped -- under a stack about JSON."""
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"version": 1, "tuning": {"max_evens": 4}}), encoding="utf-8")
    argv = ["compile", TINY_MIDI, "--settings", str(path), "--out-dir", str(tmp_path)]
    assert main(argv) == 2
    out = capsys.readouterr().out
    assert "settings:" in out
    assert "max_evens" in out
    assert not (tmp_path / "rawmap.json").exists()


# ---- the window ----


def test_a_bare_invocation_opens_the_window(monkeypatch):
    """Typing the name with nothing after it is what someone who came for the
    window does, and a usage message is not what they came for."""
    calls = _stub_window(monkeypatch)
    assert main([]) == 0
    assert calls == [{"midi": None, "settings": None}]


def test_the_ui_command_passes_the_song_and_the_settings_through(tmp_path, monkeypatch):
    """`snapmap-midi ui song.mid` opens on that song. Dropping the arguments
    would open a blank window and leave the user to find the file again in a
    dialog, having already named it."""
    calls = _stub_window(monkeypatch)
    assert main(["ui", TINY_MIDI, "--settings", "s.json"]) == 0
    assert calls == [{"midi": TINY_MIDI, "settings": "s.json"}]


def test_a_bare_invocation_with_no_display_prints_help_instead_of_hanging(monkeypatch, capsys):
    """`webview.start()` blocks until the window closes, and a window nobody
    can see never closes. In CI or over a remote shell a bare `snapmap-midi`
    would hang until it was killed, having printed nothing."""
    monkeypatch.setattr(cli_module, "_has_display", lambda: False)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage" in out
    assert "compile" in out


def test_windows_always_has_a_display(monkeypatch):
    """The game this writes maps for is Windows-only, so the ordinary user is
    on a desktop. Asking an environment variable there would answer False and
    refuse to open the window on the only platform that wants it."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert cli_module._has_display() is True


@pytest.mark.parametrize("variable", ["DISPLAY", "WAYLAND_DISPLAY"])
def test_either_display_server_counts(monkeypatch, variable):
    """Checking only DISPLAY would print usage at a Wayland desktop that can
    perfectly well show a window."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert cli_module._has_display() is False
    monkeypatch.setenv(variable, ":0")
    assert cli_module._has_display() is True


def test_the_window_says_what_to_install_when_pywebview_is_absent(monkeypatch, capsys):
    """The dependency is Windows-only, so elsewhere this message IS the whole
    experience. It has to name the command that fixes it.

    Patched through `sys.modules` rather than `builtins.__import__`: a global
    import hook catches pytest's own assertion rewriting and fails somewhere
    unrelated. A None entry makes `import webview` raise ImportError, which is
    exactly the branch under test.
    """
    monkeypatch.setitem(sys.modules, "webview", None)
    from snapmap_midi.ui import app

    assert app.run() == 2
    assert "pip install" in capsys.readouterr().out


def test_the_window_asset_folder_ships_inside_the_package(monkeypatch):
    """Resolved from the module's own file, not the working directory. A
    console script is run from wherever the user is standing, and a relative
    path would open a blank window on every directory but one."""
    from snapmap_midi.ui import app

    root = app.web_root()
    assert root.is_dir()
    assert (root / "index.html").is_file()
