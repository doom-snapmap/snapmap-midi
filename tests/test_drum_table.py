"""The user's own percussion table, and the overlay everything reads through.

`DRUM_MAP` is a taste call, and until now it was the only one available: not
liking the kick meant editing the source. These cover the file that replaces
that, and the one property that makes it safe -- the shipped table is never
written, so "put it back" always has something to put back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from snapmap_midi import paths
from snapmap_midi.music import gm
from snapmap_midi.music.analysis import analyze
from snapmap_midi.music.midi import parse_notes
from snapmap_midi.sound import palette

_SHIPPED_FILE = Path(gm.__file__).resolve().parents[1] / "data" / "drum_map.json"


def _kit(tmp_path, keys=(36, 38), name="kit.mid"):
    import mido

    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    for key in keys:
        track.append(mido.Message("note_on", channel=9, note=key, velocity=100, time=0))
        track.append(mido.Message("note_off", channel=9, note=key, velocity=0, time=120))
    path = tmp_path / name
    mid.save(str(path))
    return path


def test_the_shipped_table_is_data_and_still_names_real_sounds():
    """Moved out of source so a user table can sit beside it. A name that is no
    longer in the palette would compile to a note nothing plays."""
    raw = json.loads(_SHIPPED_FILE.read_text(encoding="utf-8"))
    assert raw, "the shipped table is empty"
    # JSON has no integer keys, so the loader converts. A regression there is
    # silent: every lookup misses and the whole kit goes quiet.
    assert {int(key): sound for key, sound in raw.items()} == gm.DRUM_MAP
    assert all(isinstance(key, int) for key in gm.DRUM_MAP)
    assert set(gm.DRUM_MAP.values()) <= set(palette.drum_sound_pool())


def test_no_user_table_means_the_shipped_one_answers():
    assert gm.user_drum_table() == {}
    assert gm.drum_table() == gm.DRUM_MAP


def test_a_saved_key_overlays_the_shipped_one_and_leaves_the_rest():
    """Overlay, not replacement. Someone who dislikes one kick still wants every
    other key, and a table that replaced wholesale would silence the kit."""
    gm.save_user_drum_table({36: "play_sfx_ben_kick_02"})
    table = gm.drum_table()
    assert table[36] == "play_sfx_ben_kick_02"
    assert table[38] == gm.DRUM_MAP[38]
    assert len(table) == len(gm.DRUM_MAP)
    # And the shipped table itself is untouched, which is what makes the change
    # undoable at all.
    assert gm.DRUM_MAP[36] == "play_noise_kick_tight"


def test_a_saved_key_can_reach_a_key_the_shipped_table_drops():
    """The exotic keys are the reason this exists. `DRUM_MAP` drops them, so
    they play nothing, and no per-song setting made them a default."""
    assert 60 not in gm.DRUM_MAP
    gm.save_user_drum_table({60: "play_clave1"})
    assert gm.drum_table()[60] == "play_clave1"


def test_saving_an_empty_table_removes_the_file():
    """"Back to shipped" is a state the next reader has to understand without
    being told, and an absent file says it more durably than `{}` does."""
    gm.save_user_drum_table({36: "play_sfx_ben_kick_02"})
    assert paths.drum_map_file().exists()
    gm.save_user_drum_table({})
    assert not paths.drum_map_file().exists()
    assert gm.drum_table() == gm.DRUM_MAP


def test_a_saved_sound_has_to_be_one_the_kit_can_use():
    """This file outlives the session that wrote it. A pitched sound holds one
    fixed note under every hit and a looping ambience is never stopped, and
    meeting that on next week's song with no memory of choosing it is worse
    than being refused now."""
    with pytest.raises(ValueError):
        gm.save_user_drum_table({36: "play_pianoc4"})
    with pytest.raises(ValueError):
        gm.save_user_drum_table({200: "play_clave1"})
    assert not paths.drum_map_file().exists(), "a refused table must not be written"


def test_an_unreadable_table_is_ignored_rather_than_fatal():
    """A truncated preference file must not cost a song. The whole feature is a
    convenience, and refusing to open anything over it trades a small loss for
    a total one."""
    path = paths.drum_map_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")
    assert gm.user_drum_table() == {}
    assert gm.drum_table() == gm.DRUM_MAP


def test_the_compile_plays_the_saved_table_not_the_shipped_one(tmp_path):
    """The point of the whole exercise. A default that the window showed and
    the compiler ignored would be worse than no feature at all."""
    mid = _kit(tmp_path)
    before, _ = parse_notes(mid, drums=True)
    assert {n.shader for n in before} == {gm.DRUM_MAP[36], gm.DRUM_MAP[38]}

    gm.save_user_drum_table({36: "play_sfx_ben_kick_02"})
    after, _ = parse_notes(mid, drums=True)
    assert "play_sfx_ben_kick_02" in {n.shader for n in after}


def test_the_song_still_wins_over_a_saved_default(tmp_path):
    """Order matters: the song is the more specific answer. A default that
    overrode the choice made for this piece would be unusable."""
    mid = _kit(tmp_path)
    gm.save_user_drum_table({36: "play_sfx_ben_kick_02"})
    notes, _ = parse_notes(mid, drums=True, drum_key_overrides={36: "play_clave1"})
    shaders = {n.shader for n in notes}
    assert "play_clave1" in shaders
    assert "play_sfx_ben_kick_02" not in shaders


def test_the_analysis_shows_a_key_falling_back_to_the_saved_table(tmp_path):
    """The window reads `drum_keys` off the analysis to draw each row. Computed
    from the shipped table alone, every row would describe a sound the compile
    was no longer playing."""
    mid = _kit(tmp_path)
    gm.save_user_drum_table({36: "play_sfx_ben_kick_02"})
    kit = [c for c in analyze(mid).channels if c.is_drums][0]
    assert kit.drum_keys[36] == "play_sfx_ben_kick_02"


def test_the_table_is_read_fresh_so_a_save_is_audible_at_once(tmp_path):
    """Caching it would leave the preview playing the old kick until restart --
    exactly the moment the change has to be audible."""
    mid = _kit(tmp_path)
    gm.save_user_drum_table({36: "play_sfx_ben_kick_02"})
    assert gm.drum_table()[36] == "play_sfx_ben_kick_02"
    gm.save_user_drum_table({36: "play_sfx_ben_kick_03"})
    assert gm.drum_table()[36] == "play_sfx_ben_kick_03"
    kit = [c for c in analyze(mid).channels if c.is_drums][0]
    assert kit.drum_keys[36] == "play_sfx_ben_kick_03"
