"""The extracted-audio cache: where it goes, what it skips, and what it names.

Runs against a synthesised install, built by the helpers in `test_wwise` --
imported rather than duplicated, because a second copy of the bank assembler
would drift from the first and the drift would show up as a cache test failing
for a format reason.

The cache directory is redirected to a temporary one for every test here. It
is a real user directory otherwise, and a suite that wrote 450 MB
of game audio into it would be a suite nobody could run twice.
"""

from __future__ import annotations

import io
import json
import pathlib
import wave

import pytest

from snapmap_midi import paths
from snapmap_midi.audio import library, locate, wwise
from test_wwise import build_bank, frame, wem, write_install

#: What the synthesised install can play. Two is enough to tell "skipped the
#: right one" from "skipped everything".
_NAMES = ["play_one", "play_two"]


@pytest.fixture(autouse=True)
def temporary_cache(tmp_path, monkeypatch):
    """Point the cache at a temporary folder for the whole module."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return library.cache_dir()


@pytest.fixture
def small_palette(monkeypatch):
    """Stand `_NAMES` in for the 890-name palette.

    `status` compares the cache against every name the palette holds, so
    without this every readiness assertion here would be measuring the shipped
    palette against two extracted sounds and reporting not-ready forever.
    """
    monkeypatch.setattr(library, "expected_names", lambda: list(_NAMES))
    return list(_NAMES)


@pytest.fixture
def fake_install(tmp_path):
    """An install holding exactly `_NAMES`."""
    media = {index: wem(frame(nibbles=[4]) * 2) for index, _ in enumerate(_NAMES, 1)}
    chains = [(name, index) for index, name in enumerate(_NAMES, 1)]
    root = tmp_path / "game"
    write_install(root, banks=[build_bank(chains, media=media)])
    return root


@pytest.fixture
def no_install(monkeypatch):
    """Hide whatever install this machine happens to have.

    Half of these tests are about the state where there is no game, and on a
    developer's machine there usually is one. Without this they would pass in
    CI and quietly test nothing here.
    """
    monkeypatch.setattr(locate, "doom_install", lambda: None)


# ---- where it goes ----


def test_the_cache_is_under_this_tools_own_folder(tmp_path):
    cached = paths.sound_cache()
    assert cached.parent.name == paths.APP_DIR_NAME
    assert cached.name == paths.SOUND_CACHE_NAME
    assert str(tmp_path) in str(cached)


def test_the_cache_is_not_inside_the_package():
    """Derived from the user's own game, rebuildable, and about a hundred
    megabytes: three reasons `pip uninstall` should not be what removes it."""
    import snapmap_midi

    package = pathlib.Path(snapmap_midi.__file__).resolve().parent
    assert package not in paths.sound_cache().resolve().parents


def test_the_expected_names_are_the_palette():
    """The palette, not the install. An install holds tens of thousands of
    media that no speaker can be pointed at."""
    from snapmap_midi.sound import palette

    expected = [sound for sounds in palette.load_palette().values() for sound in sounds]
    assert library.expected_names() == expected
    assert len(expected) == 890  # the count the decoder was proven against


# ---- status ----


def test_an_empty_cache_is_not_ready(no_install):
    state = library.status()
    assert state["ready"] is False
    assert state["count"] == 0
    assert state["expected"] == len(library.expected_names())
    assert state["install"] is None
    assert state["cache_dir"] == str(library.cache_dir())


def test_a_full_cache_is_ready(fake_install, small_palette):
    library.extract(install=fake_install)
    state = library.status()
    assert state["ready"] is True
    assert (state["count"], state["expected"]) == (2, 2)


def test_a_half_extracted_cache_is_not_ready(fake_install, small_palette):
    """60% extracted is not "mostly ready" -- it is an editor where four notes
    in ten are silent with nothing on screen saying why."""
    library.extract(install=fake_install, names=[_NAMES[0]])
    state = library.status()
    assert state["ready"] is False
    assert (state["count"], state["expected"]) == (1, 2)


def test_a_stale_cache_version_is_not_ready(fake_install, small_palette):
    """The only thing that can invalidate a cache. Audio decoded by an earlier
    reader that ran 1.56% long is still valid audio -- nothing in the files
    themselves can tell the two apart."""
    library.extract(install=fake_install)
    manifest = library.cache_dir() / library.MANIFEST_NAME
    manifest.write_text(json.dumps({"version": library.CACHE_VERSION - 1}), encoding="utf-8")
    assert library.status()["ready"] is False


def test_a_stale_cache_is_redecoded_without_needing_the_force_flag(fake_install, small_palette):
    """The window has no force checkbox, so setup itself must repair an old cache."""
    library.extract(install=fake_install)
    manifest = library.cache_dir() / library.MANIFEST_NAME
    manifest.write_text(json.dumps({"version": library.CACHE_VERSION - 1}), encoding="utf-8")
    result = library.extract(install=fake_install)
    assert (result["written"], result["skipped"]) == (2, 0)
    assert result["ready"] is True


# ---- extraction ----


def test_extract_writes_a_wav_per_name_and_a_manifest(fake_install, small_palette):
    result = library.extract(install=fake_install)
    assert result["written"] == 2
    assert result["failed"] == []
    for name in _NAMES:
        with wave.open(io.BytesIO(library.read_wav(name))) as reader:
            assert reader.getnframes() == 2 * 64
    manifest = json.loads((library.cache_dir() / library.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest == {
        "version": library.CACHE_VERSION,
        "install": str(fake_install),
        "count": 2,
    }


def test_extraction_is_resumable(fake_install, small_palette):
    """Half a minute is long enough to close a window in the middle of, and a
    run that could only start from nothing would charge for the whole thing
    again."""
    library.extract(install=fake_install, names=[_NAMES[0]])
    result = library.extract(install=fake_install)
    assert (result["written"], result["skipped"]) == (1, 1)


def test_force_redecodes_what_is_already_there(fake_install, small_palette):
    library.extract(install=fake_install)
    result = library.extract(install=fake_install, force=True)
    assert (result["written"], result["skipped"]) == (2, 0)


def test_a_half_written_file_cannot_survive_a_kill(fake_install, small_palette):
    """The failure a resumable cache introduces: the resume rule is "a file
    that exists is done", so a truncated write would be skipped forever. The
    write goes through a temporary name, and nothing partial is left behind.
    """
    library.extract(install=fake_install)
    leftovers = [p.name for p in library.cache_dir().iterdir() if p.name.endswith(".part")]
    assert leftovers == []


def test_progress_reports_every_name_and_reaches_the_total(fake_install, small_palette):
    """Skipped sounds are reported too. A resumed run that only reported what
    it decoded would sit at zero for the whole time it spends confirming what
    it already has."""
    seen = []
    library.extract(install=fake_install, names=[_NAMES[0]])
    library.extract(install=fake_install, progress=lambda *row: seen.append(row))
    assert [name for _done, _total, name in seen] == _NAMES
    assert seen[-1][:2] == (2, 2)


def test_a_sound_the_install_lacks_is_named_rather_than_counted(fake_install, small_palette):
    """ "17 sounds failed" is not something anybody can act on. Which ones
    decides whether it matters."""
    result = library.extract(install=fake_install, names=_NAMES + ["play_absent"])
    assert result["failed"] == ["play_absent"]
    assert result["written"] == 2


def test_a_name_that_would_escape_the_cache_is_refused(fake_install, small_palette):
    """Sound names come from a declaration file an override lets the user
    replace, so they are input. A name holding a separator is a path traversal
    with a game-modding costume on."""
    escape = "../" + "escaped"
    result = library.extract(install=fake_install, names=[escape])
    assert result["failed"] == [escape]
    assert not (library.cache_dir().parent / "escaped.wav").exists()


def test_extract_without_an_install_says_so(no_install):
    with pytest.raises(wwise.SoundsUnavailableError) as caught:
        library.extract()
    assert paths.DOOM_INSTALL in str(caught.value)


# ---- reading back ----


def test_reading_an_unextracted_sound_is_not_an_error():
    """A caller previewing a batch meets missing sounds routinely -- a partial
    extraction, a DLC sound in a base-game install. Each is a note that does
    not play, not a run that stops."""
    assert library.wav_path("play_one") is None
    assert library.read_wav("play_one") is None


def test_reading_an_extracted_sound_gives_the_bytes(fake_install, small_palette):
    library.extract(install=fake_install)
    assert library.wav_path("play_one").is_file()
    assert library.read_wav("play_one")[:4] == b"RIFF"


# ---- the real install ----


@pytest.mark.gamedata
def test_a_handful_of_real_sounds_extract():
    """The real chain end to end, kept to three sounds so it stays a test
    rather than a full extraction."""
    found = locate.doom_install()
    if found is None:
        pytest.skip("no game install found (see snapmap_midi.audio.locate)")
    names = ["play_pianoc4", "play_violinc4", "play_fluteb4"]
    result = library.extract(install=found, names=names)
    assert result["failed"] == []
    assert result["written"] == len(names)
    with wave.open(io.BytesIO(library.read_wav("play_pianoc4"))) as reader:
        assert reader.getnframes() > 0
