"""The decoded-audio cache: extract once, then read files.

Decoding the whole palette out of the banks takes about 36 seconds. Doing it
on demand would put that cost on the first press of every note, and doing it
at startup would put it in front of a window that otherwise opens instantly --
so it happens once, deliberately, and the result is 890 `.wav` files under the
user's local application data.

Not inside the package. The cache is derived from the user's own game and is
theirs, it is rebuildable, and it is about 450 MB: three separate reasons a
`pip uninstall` should not be the thing that removes it and a wheel should not
be the thing that carries it.

Extraction is resumable because it is interruptible. Half a minute is long
enough to close a window in the middle of, and an extraction that could only
start from nothing would make that cost the whole run again. A name whose file
is already there is skipped, so a second attempt finishes the first one.
"""

from __future__ import annotations

import json
import os
import re
import struct
from pathlib import Path
from typing import Optional

from snapmap_midi import paths
from snapmap_midi.audio import locate, wwise
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


def cache_dir() -> Path:
    """Where the extracted audio lives."""
    return paths.sound_cache()


def expected_names() -> list:
    """Every sound the cache is meant to hold: the palette, in order.

    The palette rather than the install, because the palette is what a map can
    actually name. An install holds tens of thousands of media, almost none of
    which a speaker can be pointed at, and extracting them would turn half a
    minute into an afternoon and 450 MB into many gigabytes.
    """
    return [sound for sounds in palette.load_palette().values() for sound in sounds]


def _wav_file(name: str) -> Optional[Path]:
    """The file a name maps to, whether or not it exists. None if unsafe."""
    if not _SAFE_NAME.match(name):
        return None
    return cache_dir() / ("%s.wav" % name)


def wav_path(name: str) -> Optional[Path]:
    """The cached file for a sound, or None when it has not been extracted."""
    target = _wav_file(name)
    return target if target is not None and target.is_file() else None


def read_wav(name: str) -> Optional[bytes]:
    """The cached audio for a sound, or None when there is none.

    None rather than an exception: a caller asking for a batch of sounds to
    preview is going to meet missing ones routinely -- a partial extraction, a
    DLC sound in a base-game install -- and every one of those is a note that
    does not play rather than a run that stops.
    """
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


def status() -> dict:
    """What the window needs to decide between the editor and the first-run panel.

    `ready` is deliberately strict: a matching cache version AND a file for
    every expected name. A cache that is 60% extracted is not "mostly ready" to
    anything that matters -- it is an editor where four notes in ten are
    silent, with nothing on screen saying why.

    Paths come back as strings because this crosses into the window, where a
    `Path` is not a thing that survives the trip.
    """
    names = expected_names()
    count = _cached(names)
    install = locate.doom_install()
    return {
        "ready": bool(names)
        and count == len(names)
        and _manifest().get("version") == CACHE_VERSION,
        "count": count,
        "expected": len(names),
        "install": str(install) if install is not None else None,
        "cache_dir": str(cache_dir()),
    }


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
    result = status()
    result.update({"written": written, "skipped": skipped, "failed": failed})
    return result
