# snapmap-midi: replace auditioning with a MIDI control UI

Status: approved design, 2026-08-10.

## The problem

Instrument selection is entirely automatic and entirely out of reach. A MIDI
program number lands in `gm_to_family` (`music/gm.py:34`), a ladder of twelve
band-edge tests, and whatever family falls out is what the note plays. The only
user-facing lever is `--remap`, which is family-wide and global: you cannot say
"channel 3 should be marimba", only "every violin in the file becomes a piano".
`channel_families` does exist in the library (`compile.py:54`) and has no flag,
no config file, and no way to discover what channels a file even contains.

`audition` was the workaround. It builds a second kind of map whose switch
fires every sound in one palette category 1500 ms apart, prints a numbered
legend, and leaves the user to load it in DOOM and listen. Nothing comes back:
the only way to act on what you heard is to hand-edit `gm.py` or pass
`--remap`. The loop from ear to compiler is a human retyping a table.

This replaces that loop with direct control.

## What is actually reachable

Twelve of the palette's twenty-four categories can play a pitch. The rest have
no note in their sound names, so `build_note_index` (`sound/palette.py:228`)
produces nothing for them and `decl_for` returns `None` — every note assigned
to such a family is dropped.

| Family | Sounds | MIDI range | Reachable via `gm_to_family`? |
|---|---|---|---|
| `ins_piano` | 88 | 21–108 | yes |
| `ins_marimba` | 60 | 36–96 | yes |
| `ins_violin` | 46 | 55–100 | yes |
| `ins_horns` | 44 | 34–77 | yes |
| `ins_guitar` | 43 | 40–82 | yes |
| `ins_brass_bells` | 41 | 72–112 | **no** |
| `ins_flute` | 39 | 59–97 | yes |
| `ins_trumpet` | 36 | 52–87 | yes |
| `ins_pulse` | 32 | 36–67 | yes |
| `ins_sine` | 32 | 36–67 | yes |
| `ins_square` | 32 | 36–67 | **no** |
| `ins_tri` | 32 | 36–67 | **no** |

Three families are unreachable today by any input. A picker is the only thing
that makes them addressable.

`ins_string` is listed in `SUSTAINED` (`music/gm.py:18`) and has zero pitched
sounds, so selecting it silently drops every note. The UI must not offer it.
This is a pre-existing latent bug that a picker would otherwise expose.

## What replaces hearing

Removing `audition` removes the only way to hear a game sound. Three things
replace it, and only the first two are new capability:

1. **Range fit.** Each family has a hard playable range. A channel whose notes
   fall outside it gets octave-displaced by `decl_for`. The UI computes, per
   channel and per candidate family, how many notes land outside — a number
   audition never gave, about the failure that actually degrades a song.

2. **Dry-run statistics.** Every settings change re-runs the compile without
   writing a file and reports notes, dropped, sustained, voices, events. The
   engine's emitter-slot limit is the documented failure mode
   (`docs/limits.md`); seeing the event count before export is the direct
   readout on it.

3. **Curated labels.** `data/soundfont_labels.json` carries human ear-notes
   (`heard`, `role`, `confirmed`) and is read by no code today. It covers
   `ins_noise` only — sixteen sounds. It is surfaced in the drum picker where
   it applies. It is a bonus, not a substitute.

## Architecture

A pywebview window over the existing library. No server, no sockets: a test
bans network clients from shipped modules (`tests/test_document.py:294`), and
that constraint stands.

```
snapmap_midi/
  ui/
    app.py          window creation, pywebview lifecycle
    api.py          the js_api bridge -- the ONLY surface JS can call
    session.py      per-window state: loaded file, analysis, settings
    web/
      index.html    markup
      styles.css    CSS-variable design tokens, light and dark
      app.js        rendering and bridge calls
  settings.py       the settings schema, shared by CLI and UI
  music/
    analysis.py     MIDI inspection: what channels, what programs
  data/
    gm_programs.json   the 128 General MIDI program names
```

`ui/` and `settings.py` join `compile` and `cli` at the product surface. The
subsystem layering test (`tests/test_document.py:192`) gains them, so
`rawmap`, `sound` and `music` remain unable to import them.

### Layer placement

`music/analysis.py` sits in the music layer: it reads a MIDI file and names
what it finds, using `gm` for program names and `sound.palette` for family
ranges. Both are at or below it.

`settings.py` sits at the surface. It validates a settings document and turns
it into `compile_to_rawmap` keyword arguments. It imports `sound.palette` to
reject a family that cannot play a pitch.

`ui/api.py` imports `settings`, `compile`, `music.analysis` and `paths`. It
imports pywebview nowhere — the bridge class is plain Python and fully
testable without a browser.

### The bridge

pywebview maps `js_api` methods onto `window.pywebview.api`, returning
promises. Calls arrive on separate threads and are not thread-safe, so the
session object guards its mutable state with a lock.

| Method | Returns |
|---|---|
| `pick_midi()` | native open dialog; loads the choice; the analysis, or an error |
| `load_midi(path)` | the analysis for an explicit path, or an error |
| `catalog()` | pitched families with ranges and counts; drum-capable sounds; labels |
| `get_settings()` | the current settings document |
| `apply_settings(patch)` | merges, revalidates, returns settings plus fresh dry-run stats |
| `dry_run()` | compile without writing; stats and warnings |
| `pick_out_dir()` | native folder dialog |
| `export()` | writes `rawmap.json`; destination and the same advice the CLI prints |
| `save_settings_file()` / `load_settings_file()` | native dialogs over the shared schema |

Every method returns `{"ok": true, ...}` or `{"ok": false, "error": "..."}`.
No method raises into JavaScript.

### The settings document

One JSON schema, written by the UI and readable by `--settings` on the CLI, so
a session tuned in the window can be replayed from a script.

```json
{
  "version": 1,
  "midi": "song.mid",
  "button": "snapmap-midi-song",
  "out_dir": null,
  "baseline": null,
  "channels": {
    "0": {"family": "ins_marimba", "muted": false},
    "3": {"family": null, "muted": true}
  },
  "drums": "auto",
  "drum_keys": {"38": "play_noise_clap"},
  "tuning": {
    "max_speakers": 32, "release_s": 0.1, "hard_stop": false,
    "max_events": null, "max_poly": null,
    "cap_sustain_ms": null, "bass_cap_ms": null
  }
}
```

`family: null` means "leave the automatic choice alone". Absent keys take
their defaults. Unknown keys are an error rather than a silent no-op, because
a typo in a hand-edited settings file should not compile quietly.

`channels` maps onto the existing `channel_families`. `muted` and `drum_keys`
need new library parameters.

## New library capability

Three additions, each small and each with an existing near-neighbour.

**`music/analysis.py:analyze(mid_path)`** — reads a MIDI file and returns, per
channel: the channel number, its program number and General MIDI name, note
count, lowest and highest pitch, whether it is the percussion channel, the
family `gm_to_family` would pick, and for the drum channel the set of keys
used with their `DRUM_MAP` resolution or `None`. Also the file's duration and
whether `channel_is_percussion` says channel 9 is a real kit. It parses the
file itself rather than reusing `parse_notes`, because `parse_notes` has
already collapsed program numbers into families by the time it returns.

**`channel_mutes`** — a set of channel numbers, threaded through `parse_notes`
and `compile_to_rawmap`. A muted channel contributes no notes. This is the
most direct lever on the emitter-slot limit that the tool does not have.

**`drum_key_overrides`** — `{midi_key: sound}`, consulted before `DRUM_MAP` in
`parse_notes`. The existing `drum_overrides` is keyed by resolved shader, so it
cannot distinguish two keys that map to the same sound; a per-key UI needs
per-key identity. Both are kept.

## The window

Four panels behind a tab strip, matching snapmap-plus's shell so the two tools
read as one family: a menubar with the wordmark and a light/dark toggle, a tab
strip, and a status bar carrying the live dry-run readout.

**Channels.** One row per channel present in the file: channel number, GM
program name, note count, pitch range, a family dropdown, a mute toggle, and a
fit warning when the chosen family cannot reach some of the notes. The drum
channel is marked and routes to the drums panel instead of a family dropdown.

**Drums.** Only the keys the file actually uses. Each shows its General MIDI
percussion name, its current resolution, and a dropdown of unpitched sounds.
Keys with no `DRUM_MAP` entry are listed as dropped, which is the first time
that information has been visible before compiling.

**Tuning.** The levers that reduce concurrency: drums auto/on/off, max
speakers, release, hard stop, max events, max polyphony, sustain cap, bass cap.
Each carries a one-line explanation of what it costs.

**Export.** Button name, output folder, optional baseline map, and the export
action. Afterwards it prints the same three-case destination advice the CLI
gives, because the cases are still genuinely different.

The status bar shows notes, dropped, sustained, voices and events, updated on a
debounce after every change, plus warnings in plain language: a silent map, a
family that cannot reach a channel's register, an event count in the range
where the engine starts recycling slots.

## Command line

`compile` stays. Scripts and CI keep working; every existing test that drives
it keeps passing.

- `snapmap-midi` with no arguments opens the window.
- `snapmap-midi ui [song.mid]` opens it, optionally with a file loaded.
- `snapmap-midi compile song.mid` unchanged, plus `--settings file.json`.
- `snapmap-midi audition` is removed.

pywebview is a hard dependency on Windows only —
`pywebview>=5.1; sys_platform == "win32"` — because the loader path this tool
writes to is Windows-only anyway. Other platforms get the CLI and an optional
`[ui]` extra. Tests never import pywebview: `ui/app.py` imports it inside the
launch function, so the suite and CI run unchanged on Linux.

## What is removed, and what deliberately is not

Removed: `src/snapmap_midi/audition.py`, the `audition` subparser and its two
CLI handlers, its two tests, and its sections in `README.md`,
`docs/capabilities.md` and `docs/architecture.md`.

Kept: `sound/timeline.py:author_sound_timeline`. Audition was one of two
callers; the other is a byte-identical gate (`tests/test_timeline.py:239`).
Deleting it would move a golden file for no reason. `palette.categories` and
`palette.sounds_in_category` are likewise kept — the drum picker needs them.

## Testing

The three byte-identical golden files are the safety net. This refactor must
not move a single byte of compile output; if `tiny_song_scratch.json`,
`tiny_song_hermetic.json` and the groove gate all still pass, nothing the
compiler emits has changed.

New coverage:

- `test_analysis.py` — channel inspection against the frozen `tiny.mid`,
  including a file with no program change, a file with a melodic part on
  channel 9, and pitch-range extraction.
- `test_settings.py` — schema round trip, defaults, rejection of an unknown
  key, rejection of an unpitched family, mapping onto compile keyword
  arguments.
- `test_ui_api.py` — every bridge method, with pywebview absent. Error paths
  return `ok: false` rather than raising. A dry run on `tiny.mid` reports the
  same statistics a compile does.
- `test_ui_assets.py` — a source-text contract test in the style snapmap-plus
  uses: every `pywebview.api.<name>` appearing in `app.js` must exist as a
  public method on the bridge class, and every family named in `index.html`
  must be a real pitched family. This catches bridge drift with no browser.
- `test_cli.py` — bare invocation reaches the UI entry point, `--settings`
  applies, the removed subcommand is gone.

`test_document.py` gains `settings` and `ui` in `_SURFACE`. The network ban
holds unchanged: nothing in `ui/` imports a socket.

## Risks

**A large HTML file is hard to review.** snapmap-plus's is 3,984 lines because
it had to survive being embedded in a C++ raw string literal. We have no such
constraint, so markup, style and behaviour are three files.

**Dry-run cost on a large MIDI.** A full compile per keystroke would be
unusable. The run is debounced, and the parsed MIDI is cached on the session
so only the family assignment and scheduling repeat.

**pywebview thread safety.** Bridge calls arrive on separate threads. Session
mutation takes a lock; the bridge holds no other mutable module state.
