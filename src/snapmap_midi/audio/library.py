"""Preview audio from the installed game, with the old WAV cache as fallback.

The ordinary path never extracts the palette. `DoomSounds` indexes the retail
bank metadata once, then each preview request seeks to and decodes only the
sounds used by the current converted song. The bytes stay in memory long
enough to cross the UI bridge; the browser owns the song-sized AudioBuffer
cache used by playback.

Older releases decoded all 890 sounds under the user's local application data.
Those files remain useful when DOOM has since been moved or uninstalled, so
they are still read as an offline fallback and the explicit `extract` command
still builds them. They are never required by the normal workstation path and
are never deleted automatically.

Bank discovery remains deliberately rooted at DOOM's retail sound directory.
Mods may ship banks elsewhere under the install and inject them into the live
game, but blindly merging those banks here would let an event-hash collision
silently replace a stock SnapMap sound. Custom mod sounds need an explicit
catalog and bank-priority contract of their own.
"""

from __future__ import annotations

import json
import os
import re
import struct
import threading
from pathlib import Path
from typing import Optional

from snapmap_midi import paths
from snapmap_midi.audio import locate, wwise
from snapmap_midi.music.gm import SUSTAINED
from snapmap_midi.sound import palette

#: Bumped when the decoder changes what it produces for the same input.
#:
#: This is the only thing that can invalidate a cache. The files carry no
#: internal version and there is no way to tell a wav decoded correctly from
#: one decoded by an earlier reader that was 1.56% long -- both are valid
#: audio. Without this, a fix to the decoder would ship and reach nobody who
#: had already extracted.
CACHE_VERSION = 1

#: The cache's own record, beside the audio it describes.
MANIFEST_NAME = "manifest.json"

#: What a sound name may contain to become a filename.
#:
#: The names come from a declaration file that an override lets the user
#: replace, so they are input rather than constants. A name holding a
#: separator or a parent-directory hop would write outside the cache, which is
#: an ordinary path-traversal bug with a game-modding costume on.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")

#: What a single sound is allowed to fail with without stopping the run.
#: A corrupt or absent medium is one sound the preview cannot play; it is not
#: a reason to abandon the other 889.
_SOUND_ERRORS = (KeyError, ValueError, NotImplementedError, OSError, struct.error)

#: The installed-bank index is immutable after construction and belongs to the
#: process, not to one song. Building it per sample would repeatedly walk every
#: bank header, while keeping it here costs only the object/media lookup tables
#: and leaves every compressed audio slice in the game files.
_SOURCE_LOCK = threading.RLock()
_DECODE_LOCK = threading.Lock()
_SOURCE_LOADED = False
_SOURCE_PATH: Optional[Path] = None
_SOURCE: Optional[wwise.DoomSounds] = None
_SOURCE_ERROR: Optional[Exception] = None


def cache_dir() -> Path:
    """Where the extracted audio lives."""
    return paths.sound_cache()


def expected_names() -> list:
    """Every sound the optional offline cache holds: the curated palette.

    The installed event browser is intentionally broader. The cache stays at
    890 conversion-oriented sounds so the compatibility extract command does
    not duplicate gigabytes of game data.
    """
    return [sound for sounds in palette.load_palette().values() for sound in sounds]


def _labels() -> dict:
    """Curated ear labels flattened to sound name -> short description."""
    flattened = {}
    for group in palette.sound_labels().values():
        for sound, entry in group.items():
            if isinstance(entry, dict):
                label = entry.get("heard") or entry.get("role")
            else:
                label = entry
            if label:
                flattened[sound.lower()] = str(label)
    return flattened


def _event_payload(event, categories, labels, previewable, looping_known=True) -> dict:
    """One installed catalog record in the browser's serializable shape."""
    key = event.name.lower()
    payload = {
        "id": event.event_id,
        "name": event.name,
        "path": event.path,
        "bus": event.bus,
        "environment": event.environment,
        "looping": event.looping,
        "looping_known": looping_known,
        "duration_min": event.duration_min,
        "duration_max": event.duration_max,
        "previewable": bool(previewable),
        "palette": key in categories,
    }
    category = categories.get(key)
    if category is not None:
        payload["category"] = category
    label = labels.get(key)
    if label is not None:
        payload["label"] = label
    return payload


def _palette_catalog(install=None, error=None, previewable=()) -> dict:
    """The shipped 890-name fallback when no installed catalog is readable."""
    categories = palette.sound_categories()
    labels = _labels()
    previewable = set(previewable)
    events = []
    for name in palette.all_sounds():
        category = categories[name]
        payload = {
            "id": wwise.fnv1_32(name),
            "name": name,
            "path": "snapmap_palette/%s/" % category,
            "bus": "SnapMap palette",
            "environment": "",
            "looping": category in SUSTAINED or category.startswith("amb_"),
            "looping_known": True,
            "duration_min": 0.0,
            "duration_max": 0.0,
            "previewable": name in previewable,
            "palette": True,
            "category": category,
        }
        if name.lower() in labels:
            payload["label"] = labels[name.lower()]
        events.append(payload)
    result = {
        "source": "palette",
        "install": str(install) if install is not None else None,
        "language": None,
        "count": len(events),
        "previewable_count": sum(event["previewable"] for event in events),
        "events": events,
    }
    if error is not None:
        result["error"] = str(error) or error.__class__.__name__
    return result


def _wav_file(name: str) -> Optional[Path]:
    """The file a name maps to, whether or not it exists. None if unsafe."""
    if not _SAFE_NAME.match(name):
        return None
    return cache_dir() / ("%s.wav" % name)


def wav_path(name: str) -> Optional[Path]:
    """The cached file for a sound, or None when it has not been extracted."""
    target = _wav_file(name)
    return target if target is not None and target.is_file() else None


def _read_cached_wav(name: str, cache_valid: Optional[bool] = None) -> Optional[bytes]:
    """One valid legacy cache entry, or None when it cannot be used.

    A stale decoder version is not fallback material. Both the old and new
    bytes are structurally valid WAVs, so the manifest is the only way to keep
    a fixed decoder from quietly serving its older, wrong output forever.
    Batch readers pass the already-checked validity so one song does not parse
    the same manifest once per missing sample.
    """
    if cache_valid is None:
        cache_valid = _manifest().get("version") == CACHE_VERSION
    if not cache_valid:
        return None
    target = wav_path(name)
    if target is None:
        return None
    try:
        return target.read_bytes()
    except OSError:
        return None


def _manifest() -> dict:
    """The cache's record, or {} when it is absent or unreadable."""
    try:
        return json.loads((cache_dir() / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _cached(names) -> int:
    """How many of `names` already have a file.

    One directory listing rather than one `is_file` per name: the second form
    is 890 separate filesystem calls every time the window asks whether it has
    audio, which it asks on every open.
    """
    try:
        present = set(os.listdir(cache_dir()))
    except OSError:
        return 0
    return sum(1 for name in names if ("%s.wav" % name) in present)


def _cached_names(names) -> set:
    """Names with files in the current cache version."""
    if _manifest().get("version") != CACHE_VERSION:
        return set()
    try:
        present = set(os.listdir(cache_dir()))
    except OSError:
        return set()
    return {name for name in names if ("%s.wav" % name) in present}


def reset_source() -> None:
    """Forget the process-local bank index so discovery can run again.

    The window uses this after somebody installs or moves DOOM while it is
    open. It also gives tests a clean boundary without reaching into globals.
    No files are created, changed, or held open by either reset or indexing.
    """
    global _SOURCE_LOADED, _SOURCE_PATH, _SOURCE, _SOURCE_ERROR
    with _SOURCE_LOCK:
        _SOURCE_LOADED = False
        _SOURCE_PATH = None
        _SOURCE = None
        _SOURCE_ERROR = None


def _source(refresh: bool = False) -> tuple:
    """(install, indexed banks, error) for the current retail game data."""
    global _SOURCE_LOADED, _SOURCE_PATH, _SOURCE, _SOURCE_ERROR
    install = locate.doom_install()
    path = Path(install) if install is not None else None
    with _SOURCE_LOCK:
        if refresh or not _SOURCE_LOADED or path != _SOURCE_PATH:
            _SOURCE_LOADED = True
            _SOURCE_PATH = path
            _SOURCE = None
            _SOURCE_ERROR = None
            if path is not None:
                try:
                    _SOURCE = wwise.DoomSounds(path)
                except (OSError, ValueError, struct.error, wwise.SoundsUnavailableError) as exc:
                    _SOURCE_ERROR = exc
        return path, _SOURCE, _SOURCE_ERROR


def _cache_status(names) -> dict:
    """The legacy extraction's own completion state."""
    count = _cached(names)
    install = locate.doom_install()
    ready = bool(names) and count == len(names) and _manifest().get("version") == CACHE_VERSION
    return {
        "ready": ready,
        "source": "cache" if ready else None,
        "count": count,
        "expected": len(names),
        "bank_count": 0,
        "cache_count": count,
        "install": str(install) if install is not None else None,
        "cache_dir": str(cache_dir()),
    }


def status(refresh: bool = False) -> dict:
    """What the window can preview from game banks and legacy cache together.

    `ready` remains deliberately strict: every palette sound must be available
    from the installed retail banks, the valid offline cache, or their union.
    A partial source is not "mostly ready" to an editor that promises all 890
    curated choices; it is a song whose missing notes become silent without
    warning.

    Paths come back as strings because this crosses into the window, where a
    `Path` is not a thing that survives the trip.
    """
    names = expected_names()
    install, source, source_error = _source(refresh=refresh)
    bank_names = source.names(names) if source is not None else set()
    cached_names = _cached_names(names)
    available = bank_names | cached_names
    if bank_names:
        mode = "game+cache" if cached_names - bank_names else "game"
    elif cached_names:
        mode = "cache"
    else:
        mode = None
    payload = {
        "ready": bool(names) and len(available) == len(names),
        "source": mode,
        "count": len(available),
        "expected": len(names),
        "bank_count": len(bank_names),
        "cache_count": len(cached_names),
        "install": str(install) if install is not None else None,
        "cache_dir": str(cache_dir()),
    }
    if source_error is not None:
        payload["bank_error"] = str(source_error) or source_error.__class__.__name__
    return payload


def sound_catalog(refresh: bool = False) -> dict:
    """Every named Play event from DOOM, or the shipped palette fallback.

    Names and authoring paths come from the installed soundbanksinfo.events
    file. HIRC/media resolution is reported separately as ``previewable``:
    interactive music, state transitions and legacy/DLC references remain
    valid strings for an exported map even when they have no standalone local
    sample. Nothing is extracted or copied.
    """
    install, source, source_error = _source(refresh=refresh)
    cached_names = _cached_names(expected_names())
    if source is None:
        return _palette_catalog(install, source_error, cached_names)

    try:
        events = source.event_catalog()
    except _SOUND_ERRORS as exc:
        available = source.names(expected_names()) | cached_names
        return _palette_catalog(install, exc, available)
    if not events:
        available = source.names(expected_names()) | cached_names
        return _palette_catalog(install, previewable=available)

    categories = {name.lower(): category for name, category in palette.sound_categories().items()}
    labels = _labels()
    payloads = [
        _event_payload(
            event,
            categories,
            labels,
            previewable=source.can_preview(event.name),
            looping_known=source.event_is_looping(event.name) is not None,
        )
        for event in events
    ]
    return {
        "source": "game",
        "install": str(install) if install is not None else None,
        "language": source.language,
        "count": len(payloads),
        "previewable_count": sum(event["previewable"] for event in payloads),
        "events": payloads,
    }


def event_info(name: str):
    """Installed named Play-event metadata for a name, or None."""
    _install, source, _error = _source()
    if source is None:
        return None
    try:
        return source.event(name)
    except _SOUND_ERRORS:
        return None


def event_is_looping(name: str) -> Optional[bool]:
    """Whether an installed exact event needs an explicit stop.

    None means there is no trustworthy installed record. Callers compiling a
    manually entered event can then choose the conservative behavior.
    """
    _install, source, _error = _source()
    if source is None:
        return None
    try:
        return source.event_is_looping(name)
    except _SOUND_ERRORS:
        return None


def read_wavs(names) -> dict:
    """Decode requested sounds from the game, then try offline WAVs.

    The caller already limits this list to the current conversion. One bank
    index is reused for the batch, and one decode lane prevents two overlapping
    bridge calls from making Python's CPU-bound ADPCM decoder compete with
    itself. Each bank slice is opened, read, and closed independently; DOOM and
    Steam are never held behind a long-lived file handle.
    """
    requested = list(names)
    _install, source, _error = _source()
    result = {}
    cache_valid = None
    with _DECODE_LOCK:
        for name in requested:
            data = None
            if source is not None:
                try:
                    data = source.wav_bytes(name)
                except _SOUND_ERRORS:
                    pass
            if data is None:
                if cache_valid is None:
                    cache_valid = _manifest().get("version") == CACHE_VERSION
                data = _read_cached_wav(name, cache_valid=cache_valid)
            result[name] = data
    return result


def read_wav(name: str) -> Optional[bytes]:
    """One sound from installed banks or the valid legacy cache."""
    return read_wavs([name])[name]


def _write(target: Path, data: bytes) -> None:
    """Write a cache entry so that a half-written one cannot survive.

    Through a temporary name and a rename, because the resume rule is "a file
    that exists is done". Writing in place means a run killed mid-write leaves
    a truncated wav that every later run then skips, and the sound is silently
    broken forever -- the one failure mode a resumable cache introduces that a
    non-resumable one does not have.
    """
    temporary = target.parent / (target.name + ".part")
    temporary.write_bytes(data)
    os.replace(temporary, target)


def extract(install=None, names=None, progress=None, force: bool = False) -> dict:
    """Decode the palette out of the install into the cache.

    `progress` is called with `(done, total, name)` after each sound, done
    counting from one, so a window can show a bar that reaches its end. It is
    called for skipped sounds too: a resumed run that only reported the sounds
    it decoded would sit at 0% for the twenty seconds it spends confirming
    what it already has.

    `force` re-decodes sounds that are already cached, which is what a
    `CACHE_VERSION` bump needs.

    Returns the same shape as `status`, plus what this run did. Failures are
    named rather than counted: "17 sounds failed" is not something anybody can
    act on, and the list is short enough to print.
    """
    install = install if install is not None else locate.doom_install()
    if install is None:
        raise wwise.SoundsUnavailableError(
            "no game install found -- configure %r in %s to point at one"
            % (paths.DOOM_INSTALL, paths.ENV_VAR)
        )
    wanted = list(names) if names is not None else expected_names()
    # A cache made by an older decoder is not resumable input for this one.
    # Leave the old manifest in place until the rebuild completes: if the
    # process is interrupted, the next run sees the old version and starts the
    # rebuild again instead of blessing a mixture of old and new WAVs. A
    # missing manifest is different -- it is the ordinary shape of a first
    # extraction interrupted before its final write, so those files do resume.
    manifest_path = cache_dir() / MANIFEST_NAME
    recorded = _manifest()
    if manifest_path.is_file() and recorded.get("version") != CACHE_VERSION:
        force = True
    sounds = wwise.DoomSounds(install)
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)

    written, skipped, failed = 0, 0, []
    total = len(wanted)
    for done, name in enumerate(wanted, 1):
        target = _wav_file(name)
        if target is None:
            failed.append(name)
        elif target.is_file() and not force:
            skipped += 1
        else:
            try:
                _write(target, sounds.wav_bytes(name))
            except _SOUND_ERRORS:
                failed.append(name)
            else:
                written += 1
        if progress is not None:
            progress(done, total, name)

    count = _cached(wanted)
    (directory / MANIFEST_NAME).write_text(
        json.dumps(
            {"version": CACHE_VERSION, "install": str(install), "count": count},
            indent=2,
        ),
        encoding="utf-8",
    )
    # `extract` reports whether the OFFLINE CACHE completed, not whether the
    # normal direct-bank preview could already play the same sounds. Conflating
    # those would let a failed cache build exit successfully whenever DOOM was
    # installed -- exactly when this optional command is being used.
    result = _cache_status(expected_names())
    result.update({"written": written, "skipped": skipped, "failed": failed})
    return result
