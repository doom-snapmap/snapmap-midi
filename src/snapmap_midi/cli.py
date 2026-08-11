"""Command-line surface: compile, optionally cache previews, or open the window.

The ordinary compile surface is one required argument. Everything it used to
demand -- a sound palette to point at, a saved map to inherit a timeline from,
an output name -- is either shipped, authored, or fixed by the loader. The
workstation normally reads installed game banks directly. Offline cache
extraction remains separate and optional because it needs an installed game
while a compile never does.

Typing the name with nothing after it opens the window, because the window is
now where an instrument gets chosen and this command line is where a choice
already made gets replayed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from snapmap_midi import paths
from snapmap_midi import settings as settings_module
from snapmap_midi.compile import compile_to_rawmap


def _baseline_bytes(explicit) -> bytes | None:
    """The saved map to add to, or None to author a blank one.

    An explicit path wins over a configured one; neither is the ordinary case.
    """
    path = Path(explicit) if explicit else paths.baseline_map()
    return path.read_bytes() if path else None


def _write(raw: bytes, out_dir) -> Path:
    """Write the map where the loader reads it, creating the folder if absent.

    The folder is normally created by the loader itself the first time it
    runs. Creating it here too means compiling works on a machine where that
    has not happened yet, rather than failing on a missing directory.
    """
    destination = paths.rawmap_destination(out_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return destination


def _report(destination: Path) -> None:
    """Say where the map went, and how to reach it from there.

    The three cases are genuinely different and used to be two. Writing to the
    working directory because there is no loader folder is NOT "it landed
    where the loader reads", and saying so was the same quiet wrong answer the
    old `--out` produced.
    """
    print("  -> {}".format(destination))
    if paths.destination_is_loadable(destination):
        print("     load it with `sh_rawmaps_on` in the console, then open any map")
    elif paths.loader_dir() is None:
        print("     no loader folder on this platform -- copy it to the game machine's")
        print(
            "     %LOCALAPPDATA%\\{}\\{} to play it".format(
                paths.LOADER_DIR_NAME, paths.RAWMAP_NAME
            )
        )
    else:
        print(
            "     the loader only reads {}; move it there to play it".format(
                paths.rawmap_destination()
            )
        )


#: What a compile does when nobody says otherwise -- the same values the flags
#: used to carry as their argparse defaults. They live here now because the
#: flags cannot carry them any more: see `_OVERRIDABLE`.
_COMPILE_DEFAULTS = {
    "button_name": "snapmap-midi-song",
    "drums": "auto",
    "max_speakers": 32,
    "release_s": 0.1,
    "hard_stop": False,
    "max_events": None,
}

#: Flags a settings file can also set, mapped to the compiler's own keyword.
#: Each defaults to None on the parser so that "the user typed 32" stays
#: distinguishable from "nobody said". argparse cannot tell those apart, and
#: letting the invisible default win meant `max_speakers: 8` in a file someone
#: had deliberately loaded compiled at 32 with no flag anywhere on the line --
#: the quiet wrong answer `_RetiredOut` exists to prevent, in the one feature
#: whose entire purpose is replaying a session.
_OVERRIDABLE = {
    "button": "button_name",
    "drums": "drums",
    "max_speakers": "max_speakers",
    "release": "release_s",
    "hard_stop": "hard_stop",
    "max_events": "max_events",
}

#: `--drums` is three words here and a tri-state in the compiler. Only that one
#: flag is translated: running every flag through this table turns `--button
#: off` into a switch named False, which reaches the map as a label nobody can
#: find again.
_DRUMS = {"auto": "auto", "on": True, "off": False}


def _levers(args) -> dict:
    """Built-in defaults, then the settings file, then the flags actually typed.

    Three sources in one order, and the order is the feature. A settings file
    is a decision made earlier and saved; a flag is a decision being made right
    now, so it goes last. The defaults go first so that a file setting one
    lever does not silently reset the other forty.
    """
    levers = dict(_COMPILE_DEFAULTS)
    if args.settings:
        levers.update(settings_module.to_compile_kwargs(settings_module.load(args.settings)))
    for flag, keyword in _OVERRIDABLE.items():
        typed = getattr(args, flag)
        if typed is not None:
            levers[keyword] = _DRUMS[typed] if flag == "drums" else typed
    if args.remap:
        levers["family_overrides"] = dict(kv.split("=", 1) for kv in args.remap.split(","))
    return levers


def _compile(args) -> int:
    # Checked here rather than left to the MIDI reader, which raises a bare
    # FileNotFoundError and prints a traceback at someone who mistyped a path.
    if not Path(args.midi).is_file():
        print("no such MIDI file: {}".format(args.midi))
        return 2

    try:
        levers = _levers(args)
    except settings_module.SettingsError as exc:
        # Hand editing is how this file is meant to change, so a bad one is an
        # ordinary event rather than a bug. The message names the offending
        # key; a traceback would bury that under a stack about JSON, which is
        # not the part the reader can do anything about.
        print("settings: {}".format(exc))
        return 2

    raw, stats = compile_to_rawmap(args.midi, _baseline_bytes(args.baseline), **levers)
    print("compiled {}: {}".format(args.midi, stats))
    if not stats["notes"]:
        # A map that loads and plays nothing looks exactly like success until
        # you press the switch, so say it now rather than let them find out.
        print("     WARNING: no notes were compiled -- this map will be silent")
    elif stats["dropped"]:
        print(
            "     note: {} note(s) had no sound in the palette and were dropped".format(
                stats["dropped"]
            )
        )
    _report(_write(raw, args.out_dir))
    return 0


def _extract_progress(done: int, total: int, name: str) -> None:
    """One rewritten line, not one line per sound.

    890 lines of scrollback for a step that takes half a minute buries whatever
    was printed before it, and the only number anyone reads is the last one.
    """
    if done == total or done % 25 == 0:
        print("\r  {}/{}  {:<44}".format(done, total, name[:44]), end="", flush=True)


def _extract(args) -> int:
    """Decode the game's audio into the optional offline preview cache.

    The normal workstation reads banks in place and never calls this. Keeping
    it separate preserves preview on a machine where DOOM is later moved or
    uninstalled without making a 450 MB cache part of ordinary setup.
    """
    # Imported here so the compile path does not pay for reading a palette and
    # a registry it has no use for.
    from snapmap_midi.audio import library, wwise

    try:
        result = library.extract(install=args.install, force=args.force, progress=_extract_progress)
    except wwise.SoundsUnavailableError as exc:
        print("no game audio: {}".format(exc))
        return 2
    print()
    print("  -> {}".format(result["cache_dir"]))
    print(
        "     {} decoded, {} already there, {} of {} cached".format(
            result["written"], result["skipped"], result["count"], result["expected"]
        )
    )
    if result["failed"]:
        # Named, not counted. Which sounds are missing decides whether this
        # matters -- a handful of DLC effects is not the same event as the
        # piano failing, and a bare count cannot tell them apart.
        print("     {} could not be decoded: {}".format(len(result["failed"]), result["failed"]))
    return 0 if result["ready"] else 1


def _has_display() -> bool:
    """Whether there is a screen to put a window on.

    Windows always has one, and it is the platform the game runs on, so asking
    an environment variable there would answer no and refuse to open the window
    on the only machine that wants it. Everywhere else this asks the display
    server directly, because `webview.start()` blocks until the window closes
    and a window nobody can see never closes: in CI or over a remote shell a
    bare `snapmap-midi` would hang until it was killed, having printed nothing.
    """
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _ui(args) -> int:
    # Imported here so this module stays importable where pywebview is not,
    # which is every platform but Windows.
    from snapmap_midi.ui.app import run

    return run(midi=args.midi, settings=args.settings)


class _RetiredOut(argparse.Action):
    """`--out` used to take a filename. Now it explains itself and stops.

    Without this it is not an error at all: argparse abbreviates unambiguous
    prefixes, so `--out song.json` bound to `--out-dir` and wrote
    `song.json/rawmap.json` -- creating a DIRECTORY named after the file
    someone meant to write. Silent, plausible, and wrong, which is the exact
    failure this flag was retired for.
    """

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=1, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        parser.error(
            "--out was removed. The loader reads one filename, rawmap.json, so naming "
            "the output was never a real choice.\n"
            "  to write somewhere else:  --out-dir %s" % Path(values[0]).parent
        )


def _add_compile_flags(parser) -> None:
    """Every lever a compile takes, all of them optional.

    The tuning flags default to None rather than to their real values, so that
    `_levers` can tell a typed value from an untyped one. Their defaults are in
    `_COMPILE_DEFAULTS` and are repeated in the help text here, because with no
    argparse default to show, `--help` would otherwise be the one place that
    stopped saying what a compile actually does.
    """
    parser.add_argument(
        "--out-dir",
        default=None,
        dest="out_dir",
        help="write the map to this folder instead of the loader's (the filename "
        "is always rawmap.json -- the loader reads no other name)",
    )
    parser.add_argument("--out", action=_RetiredOut, dest="_retired_out", help=argparse.SUPPRESS)
    parser.add_argument(
        "--baseline",
        default=None,
        help="add to this saved map instead of authoring a blank one",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="a settings file written by the workstation; any flag given here wins over it",
    )
    parser.add_argument("--button", default=None, help="switch label (default snapmap-midi-song)")
    parser.add_argument(
        "--remap", default=None, help='retimbre families, e.g. "ins_guitar=ins_piano"'
    )
    parser.add_argument(
        "--drums", default=None, choices=["auto", "on", "off"], help="(default auto)"
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=None,
        dest="max_speakers",
        help="voices available to sustained notes, per layer (default 32)",
    )
    parser.add_argument(
        "--release",
        type=float,
        default=None,
        help="note-off fade time in seconds (default 0.1)",
    )
    parser.add_argument(
        "--hard-stop",
        action="store_const",
        const=True,
        default=None,
        dest="hard_stop",
        help="cut notes instead of fading them",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        dest="max_events",
        help="cap the number of one-shot events",
    )


def main(argv=None) -> int:
    # allow_abbrev=False: an unambiguous prefix silently binding to a longer
    # flag is how `--out` kept working after it was removed.
    parser = argparse.ArgumentParser(
        prog="snapmap-midi",
        description="Compile playable MIDI maps, optionally cache previews, or open the window.",
        allow_abbrev=False,
    )
    # Not required: a bare `snapmap-midi` opens the window, which is what
    # someone who came for the window types.
    sub = parser.add_subparsers(dest="command")

    c = sub.add_parser("compile", help="compile a .mid into a map", allow_abbrev=False)
    c.add_argument("midi")
    _add_compile_flags(c)
    c.set_defaults(func=_compile)

    e = sub.add_parser(
        "extract", help="build an optional offline preview cache", allow_abbrev=False
    )
    e.add_argument("--install", default=None, help="read this game directory instead of searching")
    e.add_argument("--force", action="store_true", help="re-decode sounds that are already cached")
    e.set_defaults(func=_extract)

    u = sub.add_parser("ui", help="open the MIDI workstation", allow_abbrev=False)
    u.add_argument("midi", nargs="?", default=None, help="open on this song")
    u.add_argument("--settings", default=None, help="open with these settings")
    u.set_defaults(func=_ui)

    args = parser.parse_args(argv)
    if args.command is None:
        # A bare invocation opens the window. Where there is no display -- CI,
        # a shell over a remote connection, a container -- opening it would
        # block forever on a window nobody can see, so print usage instead.
        if not _has_display():
            parser.print_help()
            return 0
        return _ui(argparse.Namespace(midi=None, settings=None))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
