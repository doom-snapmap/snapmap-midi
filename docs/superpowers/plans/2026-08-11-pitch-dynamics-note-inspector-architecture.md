# Pitch, Dynamics, and Per-Note Editing Architecture

Status: implemented, then corrected by the pitch-model and channel-mix plan
Date: 2026-08-11
Scope: snapmap-midi

Current behavior is defined by
[Pitch Model and Channel Mix Correction](2026-08-11-pitch-model-and-channel-mix-correction.md).
That correction keeps the verified engine contract below but replaces target-note movement and
automatic pitch following for rootless exact SFX.

## Goal

Make the converted arrangement describe what the listener will actually hear:

- preserve MIDI note velocity;
- tune pitch-capable DOOM sounds to the note shown on the piano roll;
- expose the exact pitch and volume values used by SnapMap;
- keep browser preview and exported Timeline output on one expression model;
- let a user click any rendered note and adjust its pitch and volume;
- preserve natural playback when an exact sound has no root, with relative MIDI following as
  an explicit opt-in.

This is an expression-layer refactor, not a source-MIDI editor. The imported
MIDI file is never rewritten.

## Evidence and native contract

The implementation is based on these game-side facts.

1. Play Speaker and Update Speaker expose volumeModifier and pitchModifier.
   Their stock integer inspectors define pitch -24 through 24 and volume
   -60 through 20, both in increments of one.

2. snaphak_info/idlib.h identifies the authoring parameters as snapIntParam_t
   and the client messages as int pitchModifier and int volumeModifier.

3. Headless decompilation of DOOM 2016 RVA 0x52c620 shows both integer
   constants passed to RVA 0x52be00. The latter converts them directly to
   float, without scaling, and fills soundShaderParms_t volume.min/max and
   pitch.min/max.

       tools/re/run.ps1 decompile_rva.py -ScriptArgs @('0x52c620','0x52be00')

4. Timeline exposes fadePitch(channel, to, over). RVA 0x1853a50 prints the
   same to argument as "semitones" before passing it to the sound emitter.

       tools/re/run.ps1 decompile_rva.py -ScriptArgs @('0x1853a50','0x19b110')

5. Timeline fadeSound already has a proven rawmap shape in this repository and
   uses dB.

Therefore:

- one SnapMap pitch unit is one semitone;
- pitch is integral and clamped to -24 through 24;
- volume is integral dB and clamped to -60 through 20;
- preview detune is pitchModifier multiplied by 100 cents;
- preview gain is 10 raised to volumeModifier divided by 20.

No calibration lookup table is necessary. The editor presents generic integer
controls, but the engine path establishes their musical unit.

## Architecture

### Keep Timeline as the scheduler

Do not author a Play Speaker or Update Speaker action entity per note. Those
actions reach the same sound override fields but would require a large
connection graph with fixed parameter objects.

A controllable note schedules these events in stable order at one timestamp:

1. startSoundShader;
2. fadePitch(channel, semitones, 0), when pitch is non-zero;
3. fadeSound(channel, dB, 0), when volume is non-zero.

A sustained note keeps its existing stop or release event at note end.

### Isolate notes that need expression

Pitch and gain act on an emitter channel. A wildcard one-shot on the shared
Timeline entity cannot be adjusted independently.

All sustained notes and every decaying note with non-zero pitch or volume use
a reusable speaker voice. Neutral decaying notes retain the shared wildcard
fast path. Voice pools remain per MIDI channel, so one channel cannot steal
another channel's voice.

A decaying note reserves its voice through installed-event duration when that
metadata is available and through a conservative family fallback otherwise.
It is not explicitly stopped; the reservation prevents the next note from
cutting its natural tail.

### Stable source-note identity

Every positive MIDI note-on receives an id before mute or mapping decisions:

    channel:source-midi-note:occurrence

Changing a channel sound, muting and unmuting, or editing the note therefore
does not change its id.

Runtime note annotations carry source id and pitch, velocity, sound-root evidence, automatic
shift, playback-only pitch offset, global volume, volume trim, final modifiers, and clamp
state.
They do not alter the existing dataclass field order or rawmap key order.

### Settings schema

Settings version 2 added:

- exact-channel pitch-follow state and optional root/relative-reference metadata;
- a top-level notes mapping keyed by source id;
- per-note pitch and volume adjustments, with pitch originally stored as transpose.

Settings version 3 adds `tuning.master_volume_db`, an integral global offset from -60 through
+20 dB with a neutral zero default. Settings version 4 adds channel soloed state and renames the
sparse note pitch field to pitch_offset, making its playback-only meaning explicit. Versions 1
through 3 migrate in memory. Only choices persist; derived modifiers are recalculated.

### Root-pitch analysis

Curated pitched palette names are authoritative. Arbitrary full-game events
are analysed lazily when selected.

The analyser resolves every available leaf medium, decodes each leaf, downmixes
and downsamples bounded windows, applies a YIN-style difference and CMND
estimator, rejects weak or unstable periodicity, clusters estimates in
MIDI/cents space, and accepts a root only when usable leaves agree.

Random containers whose leaves disagree are variable, not pitched. Noise, impacts, speech,
ambience, and unsupported media are rejected as roots. A failed classifier must never invent
acoustic evidence.

For a rejected selection, Python offers the midpoint of the imported channel's lowest and
highest source notes as an optional relative natural-playback reference. The UI never calls it
a root. Natural playback is the default; MIDI intervals follow that reference only after the
user explicitly enables Follow MIDI note.

Small numeric profiles are cached by install, event, leaf media ids, and analysis version. No
game audio is copied; relative references come from MIDI and do not enter the analysis cache.

### MIDI velocity

Use a squared amplitude response:

    amplitude = (velocity / 127) ** 2
    velocity_db = 20 * log10(amplitude)

Round to the nearest integer and clamp to -60 through 0. Add the global volume offset and then
the per-note volume trim before clamping the final value to -60 through 20. Velocity 127 remains
0 dB at neutral global and note settings.

### Piano-roll truth

The roll always displays the imported MIDI pitch. Automatic root-relative tuning and the
per-note Pitch offset change playback without moving the block, changing its channel, or
selecting another curated sample.

When no root exists, a newly selected exact sound keeps natural playback. Python may persist an
optional relative reference, but Follow MIDI note remains off until the user enables it. The
inspector distinguishes natural playback, a trusted sound root, and an explicit relative
reference.

## Per-note inspector

Clicking a note opens a right-side inspector using the same design tokens,
dimensions, header, separators, and close behavior as the conversion and
notification inspectors. Clicking empty roll space continues to seek.

It shows channel, imported note, selected event, MIDI velocity, global volume, root evidence,
automatic calculation, final pitch/volume values, and any clamp. It provides:

- Pitch offset: integer -24 through 24 semitones, affecting playback only;
- volume trim: integer -60 through 20 dB;
- reset note.

Edits go through the normal settings bridge and resume playback if necessary.
The selected id survives redraws and its block stays on the imported MIDI row.
Hover glow remains pointer-only. Selection receives an outline, not a playback
animation.

## Preview/export parity

Every preview event carries the compiler's exact expression fields, including the global volume
used to resolve final dB. Web Audio sets source detune from pitchModifier, multiplies base note
gain by the final dB gain, and retains the existing master compressor and release/cut rules.
JavaScript does not reimplement root selection, velocity mapping, global-volume addition, or
clamping.

## Implementation sequence

1. Add pure expression math and root-profile tests.
2. Preserve velocity and source ids during MIDI parsing.
3. Add settings migration, channel roots, and note overrides.
4. Add multi-leaf PCM access, root analysis, and numeric cache.
5. Add fadePitch and expressive voice scheduling.
6. Share annotated preparation between compile and preview.
7. Add root-profile API and exact-sound selection integration.
8. Add note inspector, hit selection, outline, Web Audio pitch, and gain.
9. Update warnings for pitch clamps, fixed roots, and voice pressure.
10. Update README and all affected documentation.
11. Run unit, byte, packaging, lint, and available installed-game tests.

## Acceptance gates

- velocity mapping is monotonic and velocity 127 is 0 dB at neutral settings;
- global volume defaults to zero, offsets every note, and is shared by preview and export;
- pitch math is integral, deterministic, and clamped;
- ids and velocity survive overlapping or retriggered notes;
- versions 1 through 3 migrate and invalid version 4 overrides fail by name;
- tone fixtures resolve and silence/noise/unstable/mixed leaves reject;
- rejected exact sounds preserve natural playback while relative MIDI following remains an
  explicit choice;
- fadePitch raw event shape and equal-time event order are pinned;
- expressive decaying notes use isolated voices and preserve tails;
- neutral decaying notes keep shared layering;
- preview carries exactly the compiler's modifiers;
- clicking a note inspects while clicking empty space seeks;
- reset removes the persisted override;
- no source MIDI file is modified;
- pytest and Ruff pass.

## Implementation result

Implemented on 2026-08-11. The finished architecture includes:

- a single tested expression model for MIDI velocity, global volume, playback-only Pitch offset,
  root-relative pitch, integer rounding, and SnapMap clamps;
- stable source-note ids plus version 4 settings migration and sparse per-note overrides;
- authoritative curated roots, conservative lazy all-leaf analysis, natural playback for
  rootless installed-game events, and optional channel-centered relative references backed by a
  numeric-only acoustic-profile cache;
- the three scheduling paths described above, with common voice preparation shared
  by map export and browser preview;
- Web Audio detune and gain driven by the compiler's resolved values;
- exact-sound root/reference controls, natural-playback opt-out, clamp diagnostics, and the
  per-note expression inspector in the workstation UI;
- repository-wide documentation of the runtime model, settings schema, limits,
  soundbank behavior, contributor contracts, and UI behavior.

Verification completed against the final implementation:

- `ruff check .` and `ruff format --check .` passed;
- `node --check src/snapmap_midi/ui/web/app.js` passed;
- `pytest -q` passed with 627 tests and four optional installed-baseline skips;
- the saved-map marker gate reported exactly four skips;
- an isolated `pip wheel` build produced the distributable wheel;
- `git diff --check` passed.

## Non-goals

- writing edited notes into the MIDI file;
- continuous pitch bend or fractional-cent tuning;
- guessing roots for rejected sounds;
- emulating Wwise interactive music/state graphs in local preview;
- copying decoded game audio into the profile cache.
