# Pitch, Dynamics, and Per-Note Editing Architecture

Status: implemented and verified
Date: 2026-08-11
Scope: snapmap-midi

## Goal

Make the converted arrangement describe what the listener will actually hear:

- preserve MIDI note velocity;
- tune pitch-capable DOOM sounds to the note shown on the piano roll;
- expose the exact pitch and volume values used by SnapMap;
- keep browser preview and exported Timeline output on one expression model;
- let a user click any rendered note and adjust its pitch and volume;
- preserve MIDI intervals through an explicit relative reference when a sound has no root,
  while retaining fixed pitch as an opt-out.

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

Runtime note annotations carry source id, source pitch, target pitch, velocity,
root evidence, automatic shift, user trims, final modifiers, and clamp state.
They do not alter the existing dataclass field order or rawmap key order.

### Settings schema

Settings version 2 adds:

- exact-channel pitch-follow state and optional root/relative-reference metadata;
- a top-level notes mapping keyed by source id;
- per-note transpose and volume_db trims.

Version 1 sidecars migrate in memory. Existing exact-sound selections stay fixed until
reassigned or given a root/reference, preserving their old exports. New selections receive a
detected root or relative reference. Only choices persist; derived modifiers are recalculated.

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

For a rejected selection, Python chooses the midpoint of the imported channel's lowest and
highest source notes and persists it as a relative natural-playback reference. Notes follow
their MIDI intervals from that basis; the UI never calls it a root. Fixed pitch remains an
explicit pitch-follow opt-out.

Small numeric profiles are cached by install, event, leaf media ids, and analysis version. No
game audio is copied; relative references come from MIDI and do not enter the analysis cache.

### MIDI velocity

Use a squared amplitude response:

    amplitude = (velocity / 127) ** 2
    velocity_db = 20 * log10(amplitude)

Round to the nearest integer and clamp to -60 through 0. Add per-note volume
trim, then clamp the final value to -60 through 20. Velocity 127 remains 0 dB.

### Piano-roll truth

The roll displays target pitch after manual transpose; the inspector separately
shows imported pitch. Automatic root-relative tuning changes the sound to
match the target without moving the block. Manual transpose changes both.

When no root exists, a newly selected exact sound normally has a persisted relative reference
and still follows the target row. A deliberately fixed or legacy unprofiled sound has neither;
only then is the per-note pitch control a direct SnapMap modifier. The inspector labels all
three states explicitly.

## Per-note inspector

Clicking a note opens a right-side inspector using the same design tokens,
dimensions, header, separators, and close behavior as the conversion and
notification inspectors. Clicking empty roll space continues to seek.

It shows channel, imported note, selected event, MIDI velocity, root evidence,
automatic calculation, final pitch/volume values, and any clamp. It provides:

- pitch trim: integer -24 through 24 semitones;
- volume trim: integer -60 through 20 dB;
- reset note.

Edits go through the normal settings bridge and resume playback if necessary.
The selected id survives redraws; a transposed block moves to its new row.
Hover glow remains pointer-only. Selection receives an outline, not a playback
animation.

## Preview/export parity

Every preview event carries the compiler's exact expression fields. Web Audio
sets source detune from pitchModifier, multiplies base note gain by the dB gain,
and retains the existing master compressor and release/cut rules. JavaScript
does not reimplement root selection, velocity mapping, or clamping.

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

- velocity mapping is monotonic and velocity 127 is 0 dB;
- pitch math is integral, deterministic, and clamped;
- ids and velocity survive overlapping or retriggered notes;
- v1 settings migrate and invalid v2 overrides fail by name;
- tone fixtures resolve and silence/noise/unstable/mixed leaves reject;
- rejected exact sounds receive a deterministic, persisted relative reference while fixed pitch
  remains an explicit choice;
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

- a single tested expression model for MIDI velocity, note transpose, root-relative
  pitch, integer rounding, and SnapMap clamps;
- stable source-note ids plus version 2 settings migration and sparse per-note
  overrides;
- authoritative curated roots, conservative lazy all-leaf analysis, and deterministic
  channel-centered relative references for arbitrary installed-game events, backed by a
  numeric-only acoustic-profile cache;
- the three scheduling paths described above, with common voice preparation shared
  by map export and browser preview;
- Web Audio detune and gain driven by the compiler's resolved values;
- exact-sound root/reference controls, fixed-pitch opt-out, clamp diagnostics, and the per-note
  expression inspector in the workstation UI;
- repository-wide documentation of the runtime model, settings schema, limits,
  soundbank behavior, contributor contracts, and UI behavior.

Verification completed against the final implementation:

- `ruff format src tests` and `ruff check src tests` passed;
- `node --check src/snapmap_midi/ui/web/app.js` passed;
- `pytest -q` passed with 606 tests and four optional installed-baseline skips;
- `python -m build` produced both the source distribution and wheel;
- `git diff --check` passed.

## Non-goals

- writing edited notes into the MIDI file;
- continuous pitch bend or fractional-cent tuning;
- guessing roots for rejected sounds;
- emulating Wwise interactive music/state graphs in local preview;
- copying decoded game audio into the profile cache.
