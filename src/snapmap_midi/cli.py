"""Command-line surface: compile a MIDI file, or build an audition map."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from snapmap_midi import paths
from snapmap_midi.audition import DEFAULT_GAP_MS, candidates_in_category, legend
from snapmap_midi.audition import build as build_audition
from snapmap_midi.compile import compile_to_rawmap


def _resolve_baseline(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    configured = paths.baseline_map()
    if configured is None:
        sys.exit(
            "no baseline map given and none configured.\n"
            "Pass --baseline, or configure baseline_map (see snapmap_midi.paths)."
        )
    return configured


def _compile(args) -> int:
    overrides = dict(kv.split("=", 1) for kv in args.remap.split(",")) if args.remap else None
    drums = {"auto": "auto", "on": True, "off": False}[args.drums]
    raw, stats = compile_to_rawmap(
        args.midi,
        _resolve_baseline(args.baseline).read_bytes(),
        button_name=args.button,
        family_overrides=overrides,
        drums=drums,
        max_speakers=args.max_speakers,
        release_s=args.release,
        hard_stop=args.hard_stop,
        max_events=args.max_events,
    )
    Path(args.out).write_bytes(raw)
    print("compiled {}: {}".format(args.midi, stats))
    print("  -> {}".format(args.out))
    return 0


def _audition(args) -> int:
    candidates = candidates_in_category(args.category)
    if not candidates:
        print("no sounds in category {!r}".format(args.category))
        return 2
    raw = build_audition(
        candidates,
        _resolve_baseline(args.baseline).read_bytes(),
        gap_ms=args.gap,
        label="snapmap-midi-audition-" + args.category,
    )
    Path(args.out).write_bytes(raw)
    total = len(candidates) * args.gap / 1000.0
    print(
        "=== {} ({} sounds, {} ms apart, ~{:.0f}s total) ===".format(
            args.category, len(candidates), args.gap, total
        )
    )
    print("press the switch once; sounds play in this order:\n")
    print("\n".join(legend(candidates, args.gap)))
    print("\n  -> {}".format(args.out))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="snapmap-midi",
        description="Compile a MIDI file into a playable in-game music map.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compile", help="compile a .mid into a map")
    c.add_argument("midi")
    c.add_argument("--out", required=True)
    c.add_argument("--baseline", default=None, help="baseline map containing a timeline entity")
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
    a.add_argument("--out", required=True)
    a.add_argument("--baseline", default=None)
    a.add_argument("--gap", type=int, default=DEFAULT_GAP_MS)
    a.set_defaults(func=_audition)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
