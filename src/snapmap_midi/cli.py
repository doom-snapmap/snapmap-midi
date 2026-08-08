"""Command-line surface: compile a MIDI file, or build an audition map.

The whole surface is one required argument. Everything a compile used to
demand -- a sound palette to point at, a saved map to inherit a timeline from,
an output name -- is either shipped, authored, or fixed by the loader.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from snapmap_midi import paths
from snapmap_midi.audition import DEFAULT_GAP_MS, candidates_in_category, legend
from snapmap_midi.audition import build as build_audition
from snapmap_midi.compile import compile_to_rawmap
from snapmap_midi.sound.palette import categories


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


def _compile(args) -> int:
    # Checked here rather than left to the MIDI reader, which raises a bare
    # FileNotFoundError and prints a traceback at someone who mistyped a path.
    if not Path(args.midi).is_file():
        print("no such MIDI file: {}".format(args.midi))
        return 2

    overrides = dict(kv.split("=", 1) for kv in args.remap.split(",")) if args.remap else None
    drums = {"auto": "auto", "on": True, "off": False}[args.drums]
    raw, stats = compile_to_rawmap(
        args.midi,
        _baseline_bytes(args.baseline),
        button_name=args.button,
        family_overrides=overrides,
        drums=drums,
        max_speakers=args.max_speakers,
        release_s=args.release,
        hard_stop=args.hard_stop,
        max_events=args.max_events,
    )
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


def _audition(args) -> int:
    candidates = candidates_in_category(args.category)
    if not candidates:
        print("no sounds in category {!r}".format(args.category))
        print("available: {}".format(", ".join(sorted(categories()))))
        return 2
    raw = build_audition(
        candidates,
        _baseline_bytes(args.baseline),
        gap_ms=args.gap,
        label="snapmap-midi-audition-" + args.category,
    )
    total = len(candidates) * args.gap / 1000.0
    print(
        "=== {} ({} sounds, {} ms apart, ~{:.0f}s total) ===".format(
            args.category, len(candidates), args.gap, total
        )
    )
    print("press the switch once; sounds play in this order:\n")
    print("\n".join(legend(candidates, args.gap)))
    print()
    _report(_write(raw, args.out_dir))
    return 0


def _add_shared(parser) -> None:
    """Flags both subcommands take, so neither drifts from the other."""
    parser.add_argument(
        "--out-dir",
        default=None,
        dest="out_dir",
        help="write the map to this folder instead of the loader's (the filename "
        "is always rawmap.json -- the loader reads no other name)",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="add to this saved map instead of authoring a blank one",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="snapmap-midi",
        description="Compile a MIDI file into a playable in-game music map.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compile", help="compile a .mid into a map")
    c.add_argument("midi")
    _add_shared(c)
    c.add_argument("--button", default="snapmap-midi-song")
    c.add_argument("--remap", default=None, help='retimbre families, e.g. "ins_guitar=ins_piano"')
    c.add_argument("--drums", default="auto", choices=["auto", "on", "off"])
    c.add_argument("--max-speakers", type=int, default=32, dest="max_speakers")
    c.add_argument("--release", type=float, default=0.1, help="note-off fade time in seconds")
    c.add_argument(
        "--hard-stop",
        action="store_true",
        dest="hard_stop",
        help="cut notes instead of fading them",
    )
    c.add_argument(
        "--max-events",
        type=int,
        default=None,
        dest="max_events",
        help="cap the number of one-shot events",
    )
    c.set_defaults(func=_compile)

    a = sub.add_parser("audition", help="build a map that plays candidate sounds")
    a.add_argument("category", nargs="?", default="ins_noise")
    _add_shared(a)
    a.add_argument("--gap", type=int, default=DEFAULT_GAP_MS)
    a.set_defaults(func=_audition)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
