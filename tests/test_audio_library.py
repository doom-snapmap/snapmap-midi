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
from test_wwise import build_bank, build_event_catalog, frame, wem, write_install

#: What the synthesised install can play. Two is enough to tell "skipped the
#: right one" from "skipped everything".
_NAMES = ["play_one", "play_two"]


@pytest.fixture(autouse=True)
def temporary_cache(tmp_path, monkeypatch):
    """Give every test an empty disk cache and a fresh process-local bank index."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    library.reset_source()
    yield library.cache_dir()
    library.reset_source()


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


def test_installed_banks_are_ready_without_extracting(fake_install, small_palette, monkeypatch):
    """The normal path indexes the game and writes nothing under local app data."""
    monkeypatch.setattr(locate, "doom_install", lambda: fake_install)

    state = library.status()

    assert state["ready"] is True
    assert state["source"] == "game"
    assert (state["bank_count"], state["cache_count"]) == (2, 0)
    assert not library.cache_dir().exists()


def test_no_install_uses_the_shipped_palette_as_the_browser_catalog(no_install):
    catalog = library.sound_catalog()

    assert catalog["source"] == "palette"
    assert catalog["count"] == 890
    assert all(event["palette"] for event in catalog["events"])
    assert all(event["path"].startswith("snapmap_palette/") for event in catalog["events"])


def test_the_installed_browser_catalog_exposes_all_named_events_and_previewability(
    fake_install, monkeypatch
):
    folder = fake_install / wwise.SOUND_SUBDIR
    (folder / wwise.EVENT_CATALOG_NAME).write_bytes(
        build_event_catalog(
            [
                {
                    "name": "Play_One",
                    "path": "doom_test/one/",
                    "bus": "SFX_Test",
                    "looping": True,
                    "duration_min": 1.0,
                    "duration_max": 2.0,
                },
                {
                    "name": "PLAY_TWO",
                    "path": "doom_test/two/",
                    "bus": "SFX_Test",
                    "looping": False,
                    "duration_min": 0.5,
                    "duration_max": 0.5,
                },
                {"name": "Play_Missing", "path": "doom_test/missing/"},
            ]
        )
    )
    (folder / wwise.EVENT_XML_NAME).write_text(
        '<Root><Event Name="play_one" DurationType="Infinite"/>'
        '<Event Name="play_two" DurationType="OneShot"/>'
        '<Event Name="play_missing" DurationType="OneShot"/></Root>',
        encoding="utf-8",
    )
    from snapmap_midi.sound import palette

    monkeypatch.setattr(locate, "doom_install", lambda: fake_install)
    monkeypatch.setattr(
        palette,
        "sound_categories",
        lambda: {"play_one": "ins_piano", "play_two": "ins_noise"},
    )
    monkeypatch.setattr(library, "_labels", lambda: {"play_one": "Reference piano"})
    library.reset_source()

    catalog = library.sound_catalog()

    assert catalog["source"] == "game"
    assert catalog["count"] == 3
    assert catalog["previewable_count"] == 2
    assert [event["name"] for event in catalog["events"]] == [
        "Play_One",
        "PLAY_TWO",
        "Play_Missing",
    ]
    assert [event["previewable"] for event in catalog["events"]] == [True, True, False]
    assert catalog["events"][0]["path"] == "doom_test/one/"
    assert library.event_duration_ms("play_one") is None
    assert library.event_duration_ms("play_two") == 500
    assert catalog["events"][0]["bus"] == "SFX_Test"
    assert catalog["events"][0]["palette"] is True
    assert catalog["events"][0]["category"] == "ins_piano"
    assert catalog["events"][0]["label"] == "Reference piano"
    assert library.event_is_looping("PLAY_ONE") is True
    assert library.event_is_looping("play_two") is False
    assert library.event_is_looping("play_missing") is False


def test_a_game_without_named_metadata_falls_back_to_the_palette(fake_install, monkeypatch):
    monkeypatch.setattr(locate, "doom_install", lambda: fake_install)

    catalog = library.sound_catalog(refresh=True)

    assert catalog["source"] == "palette"
    assert catalog["count"] == 890


def test_a_direct_sound_decodes_in_memory_without_creating_a_wav(
    fake_install, small_palette, monkeypatch
):
    monkeypatch.setattr(locate, "doom_install", lambda: fake_install)

    with wave.open(io.BytesIO(library.read_wav("play_one"))) as reader:
        assert reader.getnframes() == 2 * 64

    assert library.wav_path("play_one") is None


def test_curated_note_name_is_authoritative_without_reading_the_install(no_install):
    profile = library.pitch_profile("play_pianoc4")
    assert profile == {
        "classification": "pitched",
        "pitchable": True,
        "root_midi": 60.0,
        "confidence": 1.0,
        "cents_spread": 0.0,
        "sources": 1,
        "source": "palette_name",
        "reason": "curated sound name identifies its note",
    }
    assert not paths.pitch_profile_cache().exists()


def test_detected_profile_cache_stores_numbers_and_never_audio(fake_install, monkeypatch):
    from snapmap_midi.audio import pitch
    from snapmap_midi.sound import palette

    monkeypatch.setattr(locate, "doom_install", lambda: fake_install)
    monkeypatch.setattr(palette, "sound_categories", lambda: {})
    calls = []

    def analyze(sources):
        calls.append(list(sources))
        return {
            "classification": "pitched",
            "pitchable": True,
            "root_midi": 57.25,
            "confidence": 0.9,
            "cents_spread": 8.0,
            "sources": len(sources),
            "reason": "stable periodic root",
        }

    monkeypatch.setattr(pitch, "analyze_sources", analyze)
    first = library.pitch_profile("play_one")
    assert first["root_midi"] == 57.25
    assert first["source"] == "detected"
    assert len(calls) == 1 and len(calls[0]) == 1
    assert paths.pitch_profile_cache().is_file()
    assert not library.cache_dir().exists()

    stored = json.loads(paths.pitch_profile_cache().read_text(encoding="utf-8"))
    assert stored["version"] == 2
    assert stored["profiles"]["play_one"]["profile"]["root_midi"] == 57.25
    assert "per_channel" not in paths.pitch_profile_cache().read_text(encoding="utf-8")

    library.reset_source()
    monkeypatch.setattr(
        pitch,
        "analyze_sources",
        lambda sources: pytest.fail("a valid numeric profile was decoded again"),
    )
    assert library.pitch_profile("play_one") == first


def test_the_bank_index_is_reused_across_status_and_sample_reads(
    fake_install, small_palette, monkeypatch
):
    monkeypatch.setattr(locate, "doom_install", lambda: fake_install)
    real_type = wwise.DoomSounds
    built = []

    def build(path):
        built.append(path)
        return real_type(path)

    monkeypatch.setattr(wwise, "DoomSounds", build)

    assert library.status()["ready"] is True
    assert library.read_wav("play_one")
    assert library.read_wav("play_two")
    assert built == [fake_install]


def test_a_full_cache_is_ready(fake_install, small_palette):
    library.extract(install=fake_install)
    state = library.status()
    assert state["ready"] is True
    assert (state["count"], state["expected"]) == (2, 2)


def test_a_complete_legacy_cache_works_after_the_game_is_removed(
    fake_install, small_palette, monkeypatch
):
    library.extract(install=fake_install)
    monkeypatch.setattr(locate, "doom_install", lambda: None)
    library.reset_source()

    state = library.status()

    assert state["ready"] is True
    assert state["source"] == "cache"
    assert (state["bank_count"], state["cache_count"]) == (0, 2)
    assert library.read_wav("play_one")[:4] == b"RIFF"


def test_offline_batch_checks_the_cache_manifest_once(fake_install, small_palette, monkeypatch):
    library.extract(install=fake_install)
    monkeypatch.setattr(locate, "doom_install", lambda: None)
    library.reset_source()
    real_manifest = library._manifest
    calls = []

    def manifest():
        calls.append(True)
        return real_manifest()

    monkeypatch.setattr(library, "_manifest", manifest)
    samples = library.read_wavs(_NAMES)

    assert all(data and data[:4] == b"RIFF" for data in samples.values())
    assert calls == [True]


def test_game_and_cache_coverage_can_complete_each_other(tmp_path, small_palette, monkeypatch):
    cache_install = tmp_path / "cache-game"
    direct_install = tmp_path / "direct-game"
    write_install(
        cache_install,
        banks=[
            build_bank(
                [("play_two", 2)],
                media={2: wem(frame(predictor=-200, nibbles=[4]) * 2)},
            )
        ],
    )
    write_install(
        direct_install,
        banks=[
            build_bank(
                [("play_one", 1)],
                media={1: wem(frame(predictor=200, nibbles=[4]) * 2)},
            )
        ],
    )
    library.extract(install=cache_install, names=["play_two"])
    monkeypatch.setattr(locate, "doom_install", lambda: direct_install)
    library.reset_source()

    state = library.status()
    samples = library.read_wavs(_NAMES)

    assert state["ready"] is True
    assert state["source"] == "game+cache"
    assert (state["bank_count"], state["cache_count"]) == (1, 1)
    assert all(data and data[:4] == b"RIFF" for data in samples.values())


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
    state = library.status()
    assert state["ready"] is False
    assert (state["count"], state["cache_count"]) == (0, 0)


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
