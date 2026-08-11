# Pitch Model and Channel Mix Correction

Status: implemented 2026-08-11.

This plan supersedes the target-note movement and automatic relative-reference defaults in
2026-08-11-pitch-dynamics-note-inspector-architecture.md. It preserves that plan's verified
SnapMap event contract, velocity mapping, voice isolation, and preview/export parity.

## Goal

Make imported MIDI, selected DOOM sounds, and SnapMap playback expression three independent
facts. The workstation should tune musical material automatically, preserve the natural
character of arbitrary game effects, and expose only the small number of decisions a musician
can use confidently.

The same pass also completes the channel interaction model:

- mute excludes one channel;
- solo auditions one or more chosen channels and mute still wins;
- channel focus changes editing visibility only;
- notes excluded by mute, solo, or conversion pressure remain visible as dimmed source data.

## Evidence

The implementation rests on contracts already verified in the repository and the DOOM 2016
SnapMap data:

1. A MIDI note supplies an integral pitch number, velocity, start, and end. Its piano-roll row
   describes the composition and is not a playback-rate control.
2. SnapMap Timeline starts a sound with startSoundShader and targets the same emitter channel
   with fadePitch and fadeSound.
3. SnapMap labels fadePitch's target as semitones. The supported integer range is -24 through
   +24. One browser-preview semitone is therefore 100 cents.
4. SnapMap volume modifiers are integral dB in the range -60 through +20. Browser preview uses
   gain = 10 raised to volume-dB divided by 20.
5. The curated palette contains musical sample families with nominal roots encoded and verified
   by the palette. The full game catalog also contains speech, impacts, noise, ambience, random
   containers, and mod events for which an acoustic root may not exist.
6. A shared one-shot emitter cannot receive note-specific pitch or gain safely. Sustains and
   expressive one-shots therefore need isolated speaker voices; neutral one-shots retain the
   shared fast path.

## Three independent axes

### MIDI composition

The MIDI source pitch is immutable conversion input. It determines the note row, stable note id,
and the musical interval the user imported. Per-note tuning never changes this value, moves the
block, changes its channel, or causes another palette sample to be selected.

### Sound source

A channel has one of three sound-source modes:

- Automatic chooses a curated musical family from the General MIDI program.
- Pitched instrument set lets the user choose a curated family.
- Exact sound triggers one full-game Play event for every note in the channel.

Curated families are multi-sample instruments. Exact sounds are single events and must not be
assumed to be instruments merely because the MIDI channel has note names.

### Playback expression

SnapMap pitch and volume modifiers describe how the chosen event is played. They do not rewrite
the MIDI composition. The per-note pitch control is consequently named Pitch offset, not
transpose.

## Pitch algorithm

### Curated musical families

For each MIDI note:

1. Select the exact palette sample when present.
2. Otherwise prefer the nearest sample with the same pitch class in another octave.
3. Otherwise use the nearest rooted sample.
4. Read that selected sample's nominal root.
5. Apply the residual difference between the MIDI note and sample root as the automatic
   SnapMap semitone modifier.

This uses the full SnapMap instrument palette instead of stretching one piano sample across the
entire keyboard. A user Pitch offset is added after the automatic residual. The offset never
changes which sample is selected.

### Exact sounds with a stable musical root

Root analysis may enable Follow MIDI note only when the decoded event has a stable, defensible
root. Random containers must have compatible leaves. Noise, speech, impacts, ambience, and
unsupported media are rejected rather than assigned a guessed octave.

For a trusted root:

    automatic = nearest integer(MIDI note - sound root)
    requested = automatic + Pitch offset
    SnapMap pitch = clamp(requested, -24, +24)

The root may be fractional; it is a pitch estimate in MIDI-note space, not merely an octave
label. The UI shows the source and confidence but does not ask ordinary users to manage them
unless they choose an exact sound.

### Exact sounds without a stable root

Rootless sounds play naturally by default:

    requested = Pitch offset
    SnapMap pitch = clamp(requested, -24, +24)

The MIDI row still describes where the event occurs in the imported composition, but it makes
no claim about the grunt, impact, or ambience's acoustic pitch. This is the safe and usually
best-sounding behavior.

Python may calculate the midpoint of the channel's imported note range as an optional relative
reference. It is stored with zero confidence and never called a detected root. Follow MIDI note
remains off until the user deliberately enables it. Once enabled, the same root-relative
formula preserves channel intervals within SnapMap's four-octave window.

The compiler does not silently fold out-of-range notes into another octave. That would change
the composition. It clamps the engine modifier and reports the limit so the user can choose a
different family, root, or arrangement.

## Volume algorithm

MIDI velocity is meaningful source data and is converted once:

    velocity dB = round(40 * log10(velocity / 127))
    velocity dB = clamp(velocity dB, -60, 0)
    requested dB = velocity dB + global volume + note volume trim
    SnapMap dB = clamp(requested dB, -60, +20)

Global Volume is the simple mix-level control in the bottom plane. Note Volume trim is an
exception tool in the note inspector. Neither changes MIDI velocity. Preview consumes the final
compiler value rather than reimplementing this calculation in JavaScript.

## User experience

### Automatic by default

Users importing an ordinary song should not tune roots or octaves. Automatic and curated
instrument choices resolve sample and pitch without more controls. A stable exact-sound root
also follows MIDI automatically.

When exact-sound analysis fails, the UI says that natural playback is preserved. It offers an
optional Follow MIDI note checkbox and one reference MIDI note in Channel settings. It does not
add more tuning sliders or imply that an arbitrary SFX has a real C3 root.

### Channel inspector

Clicking a channel row opens one focused side inspector. Its first setting is Follow MIDI note.
Automatic and curated musical mappings show the setting checked and disabled because following
is intrinsic to their pitch model. Automatic percussion shows it off and disabled because pitch
is encoded by per-key sound selection. Exact sounds make it editable and expose their detected
root or optional relative reference. This keeps a channel-wide choice out of per-note editing.

### Per-note inspector

Clicking a note pauses playback and opens one focused side inspector containing:

- MIDI note and original velocity;
- resolved sound;
- natural playback, sound root, or optional pitch reference;
- one Pitch offset control;
- one Volume trim control;
- the final SnapMap pitch and dB calculations;
- a clamp notice only when an engine boundary is reached.

The piano-roll block always stays on its imported row.

### Channel strip

Each channel row has compact M and S buttons:

- Mute always excludes that channel from preview and export.
- Solo is multi-select. When at least one S button is active, only soloed, unmuted channels play
  and export.
- Clicking the rest of a row focuses that channel for editing and opens Channel settings. Other
  notes dim and are not hit-testable; clicking the row again clears focus.

Muted and solo-excluded notes remain visible in neutral gray. This distinguishes composition
data from the current mix and avoids implying that mute deleted anything.

## State and migration

Settings version 4 adds channel soloed state and renames sparse note transpose to pitch_offset.
Versions 1, 2, and 3 migrate in memory. Every legacy notes entry keeps its integer value while
the new runtime interprets it as playback-only expression. Sidecars remain keyed by
channel:source-pitch:occurrence, so edits survive retimbre, mute, solo, and root changes.

Only source choices and user choices persist. Derived sample roots, automatic shifts, final
clamps, audio buffers, and display-only channel focus do not.

## Preview and export parity

The parser annotates every note with the same root, offset, velocity dB, final modifier, and mix
state used by map export. The preview manifest has two deliberate views:

- events contains only audible notes that survive conversion preparation and is the transport's
  audio schedule;
- display_events contains every mapped source note, including muted, solo-excluded, and
  polyphony-thinned notes, for truthful piano-roll rendering.

JavaScript applies pitch_modifier times 100 cents and the final volume_db gain. It never chooses
a sample, detects a root, recalculates velocity, or changes mixer inclusion.

## Acceptance criteria

- A per-note Pitch offset changes SnapMap playback but never note row, channel, id, or curated
  sample choice.
- Curated families use their available multi-sample palette and residual tuning.
- A trusted exact-sound root follows MIDI automatically.
- A rejected exact sound starts at natural playback and exposes relative following as opt-in.
- Final pitch and volume clamp at the verified SnapMap limits and report the request.
- Preview and exported Timeline events use the same final modifiers.
- Multiple soloed channels play together; mute overrides solo.
- Muted and solo-excluded notes remain visible but never preview or export.
- Channel focus limits note hit-testing without changing conversion state.
- Versions 1 through 3 load as version 4 and legacy note offsets retain their values.
- The full automated test suite and JavaScript syntax gate pass.

## Validation

- `ruff check .` and `ruff format --check .` pass.
- `node --check src/snapmap_midi/ui/web/app.js` passes.
- `pytest -q` passes with 627 tests and four optional installed-baseline skips.
- The saved-map marker gate reports exactly four skips.
- An isolated `pip wheel` build produces the distributable wheel.
- `git diff --check` passes.

## Explicit non-goals

This design does not claim a root for every game event, infer musicality from a filename prefix,
transpose MIDI source data, add a general note editor, or automatically time-stretch one-shot
durations. Duration behavior remains governed by measured event duration, sustain caps, release,
hard-stop, speaker, and polyphony controls until an engine-supported time-scaling contract is
proven.
