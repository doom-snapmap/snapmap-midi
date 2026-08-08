# Capabilities

Everything the tool exposes. For how the pieces fit together see
[`architecture.md`](architecture.md); for the engine limit most of the tuning exists to work
around see [`limits.md`](limits.md).

## Commands

Two subcommands. Neither needs anything configured.

```bash
snapmap-midi compile song.mid
snapmap-midi audition ins_noise
```

Both also run as a module, which is handy when the package is installed but its scripts
directory is not on `PATH`:

```bash
python -m snapmap_midi compile song.mid
```

## Where the map goes

**The map loader reads exactly one file: `rawmap.json`, in `%LOCALAPPDATA%\snapmap-plus\`.**
Not a directory it scans, not a name you give it — one hardcoded path.

So that is where both commands write, and the folder is created if it isn't there yet. The
loader creates it too, the first time it runs; doing it here as well means compiling works
on a machine where that hasn't happened.

`--out-dir` moves the folder. It does not rename the file, because a map named anything else
cannot be loaded without being renamed first:

```bash
snapmap-midi compile song.mid --out-dir D:/songs/bach
```

The old `--out` flag is gone. It let you write `song.json`, which looked like a finished
build and was not loadable by anything — you had to know, from somewhere else, to rename it.
Choosing that name was never a real choice.

To play a compiled map: open the console with `~`, run `sh_rawmaps_on`, then open any map.
Yours loads instead of it. Run `sh_rawmaps_off` when you're done.

### `compile` — a MIDI file to a playable map

| Flag | Type | Default | What it does |
|---|---|---|---|
| `midi` | path | *required* | the `.mid` to compile |
| `--out-dir` | path | the loader's folder | write to this folder instead (filename stays `rawmap.json`) |
| `--baseline` | path | none | add the song to this saved map instead of authoring a blank room |
| `--button` | text | `snapmap-midi-song` | display name of the switch that plays the song |
| `--remap` | text | none | retimbre families, e.g. `ins_guitar=ins_piano`; comma-separate several |
| `--drums` | `auto` / `on` / `off` | `auto` | `auto` includes drums when the file has a channel-9 track |
| `--max-speakers` | int | `32` | ceiling on dedicated speaker voices |
| `--release` | seconds | `0.1` | note-off fade time |
| `--hard-stop` | flag | off | cut notes instead of fading them |
| `--max-events` | int | none | cap the number of one-shot events |

On success it prints the statistics summary and the output path. The summary is worth
reading: `voices`, `decaying`, `sustained` and `notes` tell you at a glance whether the
arrangement is inside the engine's comfortable range.

### `audition` — hear what a category contains

The sound palette has hundreds of entries whose names do not tell you what they sound like.
`audition` builds a map that plays every sound in a category in sequence and prints a
numbered legend, so you can listen through with the list in front of you and find out.

| Flag | Type | Default | What it does |
|---|---|---|---|
| `category` | text | `ins_noise` | which palette category to play |
| `--out-dir` | path | the loader's folder | write to this folder instead |
| `--baseline` | path | none | add to this saved map instead of authoring a blank room |
| `--gap` | ms | `1500` | spacing between sounds |

Exits `2` if the category is empty, rather than writing a map that plays nothing, and prints
the categories that do exist.

The 24 categories: `amb_air`, `amb_hellish`, `amb_hums`, `dlc1_ui_user_defined`,
`dlc2_classicsfx`, `eff_explosions`, `eff_gore`, `eff_miscellaneous`, `ins_brass_bells`,
`ins_flute`, `ins_guitar`, `ins_horns`, `ins_marimba`, `ins_noise`, `ins_percussion`,
`ins_piano`, `ins_pulse`, `ins_sine`, `ins_square`, `ins_string`, `ins_synth`, `ins_tri`,
`ins_trumpet`, `ins_violin`.

## Tuning levers

**Every lever below reduces how many sounds are live at once.** That is the one thing they
have in common, and it is why they exist: the engine recycles sound emitter slots under
load, and a note whose slot is recycled can no longer be stopped. Read
[`limits.md`](limits.md) before reaching for any of them — a sparse arrangement needs none.

Some are on the command line; the rest are library-only arguments to `compile_to_rawmap`.
They are not hidden so much as unproven — they were added while tuning specific songs, and
promoting one to a flag is a welcome pull request.

| Lever | CLI | Type | Reach for it when |
|---|---|---|---|
| `max_speakers` | `--max-speakers` | int | too many simultaneous sustained voices; the cheapest global limit |
| `release_s` | `--release` | seconds | note-offs sound abrupt, or notes bleed together |
| `hard_stop` | `--hard-stop` | flag | a fade is still audible under the next phrase; cuts instead |
| `max_events` | `--max-events` | int | the timeline is too dense overall |
| `family_overrides` | `--remap` | dict | an instrument picked the wrong-sounding family |
| `drums` | `--drums` | mode | percussion is dominating, or is wanted and absent |
| `max_poly` | — | int | a chord-heavy passage overruns the emitter budget |
| `cap_sustain_ms` | — | ms | long held notes are the problem; truncates them |
| `bass_cap_ms` | — | ms | only the low register rings on; pairs with `bass_pitch` |
| `bass_pitch` | — | note | where "bass" starts for `bass_cap_ms`; defaults to 78 |
| `min_sustain_ms` | — | ms | very short sustained notes are wasting voices |
| `drop_sustain_over_ms` | — | ms | drop sustained notes longer than this outright |
| `family_caps` | — | dict | one instrument is monopolising voices; cap per family |
| `decaying_families` | — | set | force a family down the fire-and-forget path |
| `channel_families` | — | dict | override the family for a whole MIDI channel |
| `drop_shaders` | — | set | one specific sound is wrong; exclude it |
| `drum_overrides` | — | dict | remap individual percussion notes |
| `low_split` | — | — | split the low register onto its own family |
| `note_index` | — | index | supply a prebuilt palette index instead of resolving one |

Notes held under about a second cut reliably. That is the practical target when tuning.

## Library use

The whole compiler is importable. `compile_to_rawmap` is bytes-out and touches neither the
network nor the filesystem beyond reading the MIDI path you hand it.

```python
from snapmap_midi.compile import compile_to_rawmap

raw, stats = compile_to_rawmap("song.mid", button_name="my-song", max_poly=8)
```

Pass baseline bytes as the second argument to add the song to a map you already have:

```python
raw, stats = compile_to_rawmap("song.mid", my_level_bytes, button_name="my-song")
```

The timeline layer is usable on its own when you want to place sounds directly rather than
compile a file:

```python
from snapmap_midi.sound.timeline import author_sound_timeline

raw = author_sound_timeline(
    [("play_noise_kick_tight", 0), ("play_noise_hat", 400)],
    button_name="my-groove",
)
```

The palette answers what a sound is and which one plays a pitch:

```python
from snapmap_midi.sound.palette import build_note_index, decl_for, sounds_in_category

index = build_note_index()
decl_for("ins_piano", 60, index)  # 'play_pianoc4'
sounds_in_category("ins_noise")  # every noise sound, in declaration order
```

And the authoring core knows nothing about music, so it can build any map:

```python
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map

doc = SnapMapDocument(data=blank_map(), palette_refs=PRODUCT_PALETTE_REFS)
uid = doc.add_speaker(sound="play_pianoc4", position=(0.0, 0.0, 0.0))
```
