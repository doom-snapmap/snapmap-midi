"""The command-line surface, and the output contract in particular.

The destination is the part of this tool a user is most likely to get wrong,
and it used to be impossible to get right by accident: `--out` accepted any
filename and the loader reads exactly one. These tests pin the contract that
replaced it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from snapmap_midi import paths
from snapmap_midi.cli import main
from snapmap_midi.rawmap.codec import deserialize

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_MIDI = str(FIXTURES / "tiny.mid")


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


def test_missing_midi_file_is_a_clean_error(tmp_path, capsys):
    """Not a traceback. Mistyping a path is the most ordinary mistake there
    is, and the MIDI reader's bare FileNotFoundError is not an answer."""
    assert main(["compile", str(tmp_path / "nope.mid"), "--out-dir", str(tmp_path)]) == 2
    assert "no such MIDI file" in capsys.readouterr().out
    assert not (tmp_path / "rawmap.json").exists()


def test_unknown_category_lists_the_real_ones(tmp_path, capsys):
    """Exits 2 rather than writing a map that plays nothing, and says what
    does exist -- the names are not guessable."""
    assert main(["audition", "not-a-category", "--out-dir", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "ins_noise" in out and "ins_piano" in out
    assert not (tmp_path / "rawmap.json").exists()


def test_audition_writes_a_playable_map(tmp_path, capsys):
    assert main(["audition", "ins_noise", "--out-dir", str(tmp_path)]) == 0
    assert (tmp_path / "rawmap.json").is_file()
    out = capsys.readouterr().out
    assert "play_noise_hat" in out  # the legend, so a listener can follow along


def test_baseline_flag_adds_to_a_supplied_map(tmp_path, minimal_timeline_map):
    """The path that used to be mandatory still works, now as an option."""
    baseline = tmp_path / "level.json"
    baseline.write_text(json.dumps(minimal_timeline_map), encoding="utf-8")
    assert (
        main(["compile", TINY_MIDI, "--baseline", str(baseline), "--out-dir", str(tmp_path)]) == 0
    )
    obj = deserialize((tmp_path / "rawmap.json").read_bytes())
    # The supplied map's own timeline was reused, not a second one authored.
    timelines = [
        e
        for e in obj["entities"]
        if (e.get("entityDef") or {}).get("className") == "idTarget_Timeline"
    ]
    assert len(timelines) == 1
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
    assert paths.rawmap_destination() == Path(tmp_path) / "rawmap.json"
