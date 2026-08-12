# Contributing to snapmap-midi

This guide takes you from a fresh machine to an open pull request. For what the tool does
see [`capabilities.md`](capabilities.md), for how it works see
[`architecture.md`](architecture.md).

If anything here is wrong, missing, or unclear, fixing it is itself a welcome pull request.

## Contents

1. [Ground rules](#1-ground-rules)
2. [Setup](#2-setup)
3. [Game data](#3-game-data)
4. [Running the suite](#4-running-the-suite)
5. [Style](#5-style)
6. [Opening a pull request](#6-opening-a-pull-request)

## 1. Ground rules

**Clean-room.** Every line here is written from our own work. Do not paste in decompiled
output or copyrighted game content — not into code, not into comments, not into a test
fixture. If you learned something by reading the game's data, describe the finding and write
your own implementation of it.

**No game data, ever.** No `.decl` files. No saved maps. No committed audio. Sound *names* do
ship — they are identifiers, not content — and normal preview reads the user's installed banks
without copying them. An explicit offline cache may be generated under the user's application-data
folder, never inside the checkout. The line is drawn in
[`game-data.md`](game-data.md). CI enforces it and will fail the pull request.

**One change per pull request.** A rename bundled with a behaviour change makes both harder
to review and makes a byte-gate movement ambiguous.

## 2. Setup

Python 3.12 or newer. Nothing to find or configure — pip fetches the two runtime
dependencies. `mido` reads MIDI files. `pywebview` is the MIDI workstation and is declared for
Windows only, so on Linux or macOS add the `[ui]` extra to the install line below if you are
working on the window. The suite does not need it: `ui/api.py` and `ui/session.py` import
pywebview nowhere, and `ui/app.py` imports it inside a function, which is what keeps the
whole package importable and testable on a machine that will never open one.

```bash
git clone https://github.com/doom-snapmap/snapmap-midi.git
cd snapmap-midi
py -3.12 -m venv .venv          # Windows
python3.12 -m venv .venv        # Linux / macOS
```

Install into it in editable mode with the dev extras. These call the environment's
interpreter by path, so they work whether or not you have activated it:

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"    # Windows
.venv/bin/python -m pip install -e ".[dev]"            # Linux / macOS
```

The `src/` layout means the package is **not** importable from the repository root without
that install. That is deliberate: it makes a green suite prove the installed package works,
not just the checkout.

Check it:

```bash
.venv/Scripts/python.exe -m snapmap_midi --help        # Windows
.venv/bin/python -m snapmap_midi --help                # Linux / macOS
```

If you would rather type `python` and `pytest` bare, activate the environment first — the
[README](../README.md#the-isolated-way-recommended) has the activation line for each shell,
including the PowerShell execution-policy fix. Every command in this guide works either way.

## 3. Game data

You need none. The sound palette ships with the package and maps are authored from nothing,
so a fresh clone compiles real songs and runs the whole suite green.

The five `gamedata`-marked audio tests are the exception in the literal sense: they run only
when a real install can be found and otherwise skip. Bank parsing, direct providers, decoding,
offline fallback, mod isolation, and UI behaviour are covered with synthetic data and need no game.

Four tests compile *against* a saved map, to prove that path still works for people adding
music to a level they already have. They carry the `savedmap` marker and skip when none is
configured. **Seeing them skip is normal and not a failure.**

The suite hides `SNAPMAP_MIDI_PATHS` from every test that has not asked for it, so your own
overrides cannot change the result. That matters: without it, a contributor who had
`palette_decl` configured for their game version ran a different suite than CI did, and nine
tests failed for reasons that had nothing to do with any code change. `savedmap` tests see
the map overrides and still not the palette one — every byte gate is recorded against the
shipped palette, so letting another palette through would compare output to a golden built
from different sounds.

If you want to run them, see [`game-data.md`](game-data.md). One of them also needs
`groove_fixture`, an artifact that is not distributed and will skip permanently even for a
fully configured contributor.

## 4. Running the suite

```bash
python -m pytest
```

Four `savedmap` tests skip when no saved-map artifacts are configured. Five `gamedata` tests
also skip when no DOOM install is available. Those skips are expected; avoid pinning the
overall pass count here because every added regression test changes it.

### What the byte gates mean

Three tests compare compiler output byte for byte against a recorded artifact. If one moves,
**read [`limits.md`](limits.md) before doing anything else.**

The short version: bytes moving while the structural assertions still pass is a regression,
not an improvement. The map format preserves key insertion order, so a structurally
identical refactor can change the bytes. Find the reordered structure and restore its
order — do not re-record the fixture.

If output genuinely should change, the commit must touch the compiler, say in words what
semantic change is intended, and show which statistics moved.

### The structural guards

A handful of tests in `tests/test_document.py` assert properties of the repository rather
than of any function: that each subsystem imports only downward, that no shipped module
reaches for a network client, that the protected method names have not been renamed.

They look like bureaucracy and are not. The layering one is what keeps `rawmap/` promotable
to its own library and `sound/` usable without a MIDI compiler; the network one is what
keeps this package a pure bytes-out tool.

The layering test is data-driven over the subsystem list, and it fails if a named package is
missing rather than scanning an empty directory and passing vacuously. Its predecessor
matched modules by bare name and would have gone quiet the moment they moved into packages.

### Working on the MIDI workstation

Open `src/snapmap_midi/ui/web/index.html` in an ordinary browser. There is no bridge there,
so the window shows its empty state rather than throwing — that is deliberate, because
opening the file directly is how anybody iterating on the markup will look at it.

Everything that changes the conversion is decided in Python. The preview manifest contains
stable note id, immutable source pitch, velocity, resolved sound, playback-basis evidence,
nullable automatic pitch, playback-only pitch adjustment, initial/current/global/final dB, clamp
state, effective start/end, sustain behavior, speaker-reuse cutoffs, and audible/muted/solo
flags. `events` is the audible conversion; `display_events` retains inaudible notes for the
piano roll. Compiler and preview share `prepare_voice_layers`.
JavaScript may choose the display list and convert Python's facts to canvas coordinates, Web
Audio time, cents, and linear gain. It must not calculate a root or relative reference, resolve
a family or curated sample, repeat velocity/global volume math, reapply a clamp/engine limit,
move a note to another pitch row, or invent conversion events.

The same rule bans hard-coded sound families or game events from markup. The startup catalog
derives automatic and pitched-family choices from the shipped 24-category, 890-identifier
palette. The complete installed catalog, lazy numeric root profile, and Python-calculated
optional channel reference arrive through bridge calls when a sound is browsed and selected.
A trustworthy musical pitch may enable following automatically after octave-fitting. Tonal but
root-ambiguous material uses a channel-centered reference; clearly nonmusical material keeps
natural playback until the user explicitly enables relative following.
Preserve folder indexing, global search, bounded pagination, and the rule that root analysis
never blocks export; rendering every installed event as a live select option or DOM row is a

The shared design contract comes from Snapmap Plus: the light and dark tokens, Segoe UI and
Consolas roles, 30 px menu bar, fields, buttons, status bar, toast, brand asset, window
controls, and eight resize grips must stay exact. `tests/test_ui_assets.py` pins those
primitives. The traditional File/Playback/Options/View menus, unified track list, canvas
piano roll, global transport, bottom control plane, and side inspectors extend that language;
they do not redefine it. The roll's full MIDI axis, synchronized rulers, tempo-aware grid,
native scrolling, zoom, playback follow, and resizable channel split are one coordinate
system; a change to one must retain the asset-contract tests for all of them. Control icons
come only from the curated inline Lucide sprite in `index.html`; add one symbol and its asset
assertion when a new icon is actually needed rather than adding an icon runtime or external
fetch. Keep `LUCIDE_LICENSE.txt` in the shipped `web/` assets. Do not reintroduce tabs or
per-row Play controls.

Audio previews are optional and local. Use synthetic fixtures for compact event-catalog
parsing, XML loop overlays, localized bank indexing, direct decoding, fallback, and
mod-isolation work. Root-analysis tests must synthesize tones, silence, noise/unstable cases,
and agreeing/disagreeing container leaves in memory; never turn decoded game media into a
fixture. Numeric pitch-profile cache tests use temporary JSON and must assert that no PCM is
written.

Running `snapmap-midi extract` against a real install is an explicit offline-audio-cache test
that writes roughly 450 MB under the user's application-data folder, not the checkout; never
turn that cache into a fixture.

To see it running, `.venv/Scripts/python.exe -m snapmap_midi`. [`ui.md`](ui.md) describes
what should be on screen.

## 5. Style

```bash
ruff check .
ruff format .
```

Both run in CI and both must be clean.

**The lint ruleset is deliberately narrow** — `E`, `F`, `I` only. It was kept that way for
the initial commit so that any movement in a byte gate would have exactly one possible
cause. Broadening it (`UP`, `B`, and friends) is a genuinely useful contribution; do it as
its own pull request, with the byte gates green before and after, and not mixed into a
change that also touches behaviour.

Line length is 100.

## 6. Opening a pull request

Fill in the template. The checklist is short and each item exists because of something that
actually went wrong.

CI runs two gates on every pull request:

- **Guard (secretless)** — no game data, no unexpected binaries, secret scan, and the
  structural guards. Runs with a read-only token and no repository secrets, so it is safe on
  a fork.
- **Test (Windows + Ubuntu)** — lint and the full suite on both platforms.

A maintainer reviews before merge. Changes to `.github/` or `pyproject.toml` require
maintainer review specifically — those are the supply-chain-critical surfaces.

Merges to `main` need both gates green, one approving review, and all conversations
resolved.
