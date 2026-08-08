"""The shipped sound palette, its cache, and the override that can replace it.

The palette went from a file the user had to supply to package data, which
moved a whole class of failure from "it refuses to start" to "it quietly
resolves different sounds". These tests are about that class.
"""

from __future__ import annotations

import json

import pytest

from snapmap_midi import paths
from snapmap_midi.sound import palette


def test_the_shipped_palette_is_present_and_plausible():
    shipped = json.loads(palette._SHIPPED.read_text(encoding="utf-8"))
    categories = shipped["categories"]
    assert len(categories) == 24
    assert sum(len(v) for v in categories.values()) == 890
    # Declaration order is load-bearing: `audition` prints an index against
    # each sound, and re-sorting would renumber every legend anyone wrote down.
    assert categories["ins_noise"][0] == "play_noise_clap"


def test_load_palette_hands_out_a_copy():
    """The parse behind it is cached and shared. Handing out the cached object
    lets one caller's mutation change what every later compile resolves."""
    first = palette.load_palette()
    first["ins_piano"] = ["nonsense"]
    first["ins_noise"].clear()
    assert palette.load_palette()["ins_piano"] != ["nonsense"]
    assert palette.sounds_in_category("ins_noise"), "the shared parse was mutated"
    assert palette.build_note_index()["ins_piano"], "the shared parse was mutated"


def test_cache_clear_reparses_the_same_path(tmp_path, monkeypatch):
    """The cache is keyed on the SOURCE, not its contents. Regenerating a
    palette in place and reading it again must not return the old parse."""
    decl = tmp_path / "speaker.decl"

    def write(sound):
        decl.write_text(
            'sound = "%s"; text = "x"; desc = "y"; category = "#str_snap_3dsnd_ins_piano_title";'
            % sound,
            encoding="utf-8",
        )

    write("play_pianoc4")
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(decl)}))
    assert palette.sounds_in_category("ins_piano") == ["play_pianoc4"]

    write("play_pianod4")
    assert palette.sounds_in_category("ins_piano") == ["play_pianoc4"], "expected the cached parse"
    palette.cache_clear()
    assert palette.sounds_in_category("ins_piano") == ["play_pianod4"]


def test_the_override_actually_overrides(tmp_path, monkeypatch):
    decl = tmp_path / "speaker.decl"
    decl.write_text(
        'sound = "play_flutea9"; text = "x"; desc = "y"; '
        'category = "#str_snap_3dsnd_ins_flute_title";',
        encoding="utf-8",
    )
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(decl)}))
    palette.cache_clear()
    assert palette.categories() == ["ins_flute"]
    assert palette.sounds_in_category("ins_flute") == ["play_flutea9"]


def test_a_configured_but_missing_override_warns(tmp_path, monkeypatch):
    """Silence means a typo degrades into the shipped palette and the tool
    reports success while ignoring the thing you asked it to use."""
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(tmp_path / "nope.decl")}))
    with pytest.warns(RuntimeWarning, match="palette_decl"):
        assert paths.palette_decl() is None


def test_an_override_that_parses_to_nothing_raises(tmp_path, monkeypatch):
    """An empty index would compile to a silent map, which looks like success
    -- the exact failure PaletteUnavailableError exists to prevent."""
    decl = tmp_path / "empty.decl"
    decl.write_text("this file contains no sound declarations at all", encoding="utf-8")
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(decl)}))
    palette.cache_clear()
    with pytest.raises(palette.PaletteUnavailableError):
        palette.build_note_index()


def test_the_suite_does_not_read_the_ambient_override(monkeypatch):
    """The autouse fixture in conftest hides SNAPMAP_MIDI_PATHS. Without it a
    contributor with their own palette configured runs a different suite than
    CI does -- seven tests failed that way, none of them for a real reason."""
    import os

    assert os.environ.get(paths.ENV_VAR) is None
    assert paths.palette_decl() is None
    assert len(palette.categories()) == 24
