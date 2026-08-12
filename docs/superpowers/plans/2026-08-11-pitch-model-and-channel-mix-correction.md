# Pitch Model and Channel Mix Correction

Status: implemented and reconciled with full-range/chime field tests 2026-08-11.

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
   +24. Wwise applies that value as resampled Voice Pitch; +12 doubles playback speed.
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
the MIDI composition. The per-note pitch control is consequently named Pitch adjustment, not
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
entire keyboard. A user Pitch adjustment is added after the automatic residual. The adjustment never
changes which sample is selected.

### Exact sounds with a stable musical root

Root analysis may enable Follow MIDI note only when the decoded event has a stable, defensible
root. Random containers must have compatible leaves. Noise, speech, impacts, ambience, and
unsupported media are rejected rather than assigned a guessed octave.

For a trusted root:

    automatic = nearest integer(MIDI note - sound root)
    requested = automatic + Pitch adjustment
    SnapMap pitch = clamp(requested, -24, +24)

The root may be fractional; it is a pitch estimate in MIDI-note space. Its pitch class is
preserved while an octave-equivalent reference is chosen to minimize range overflow. The UI
shows this as detected pitch/reference evidence rather than asking ordinary users to audit math.

### Exact sounds without a stable root

Rootless sounds play naturally by default:

    requested = Pitch adjustment
    SnapMap pitch = clamp(requested, -24, +24)

The MIDI row still describes where the event occurs in the imported composition, but it makes
no claim about the grunt, impact, or ambience's acoustic pitch. This is the safe and usually
best-sounding behavior.

A tonal event whose periodic candidate is contradicted by lower dominant spectral energy is
root-ambiguous rather than unpitched. It automatically follows MIDI from the channel midpoint,
stored with zero confidence and never called a detected root. Clearly nonmusical media retains
that midpoint only as an optional reference and keeps natural playback until the user opts in.

The compiler does not silently fold out-of-range notes into another octave. That would change
the composition. It clamps the engine modifier and reports the limit so the user can choose a
different family, root, or arrangement.

### Exact-sound planning and the four-octave limit

Detection supplies evidence, not a final playback octave. For a trusted detected pitch, the
planner considers octave-equivalent references and chooses the one that minimizes overflow for
the imported channel while preserving pitch class. For example, a B5 estimate on a C2-B5 test
range uses B3 as the playback reference, yielding -23 through +24 instead of flattening the
lower half of the song at -24.

A bell or chime may be dominated by upper partials. If the periodic candidate sits above a
stronger lower spectral component, it is classified as tonal-but-root-ambiguous rather than
accepted as a root. Those sounds automatically follow the MIDI contour from the channel midpoint.
Clearly nonmusical material continues to use natural playback by default.

The old numeric profile cache is invalidated by `pitch-profiles-v2.json`. Because an old automatic
result may also be embedded in a song sidecar, enabled `root_source: detected` entries are
revalidated when that song opens. Manual/relative references and disabled pitch following are
never rewritten, and unavailable game media leaves the saved value intact. Pitch-limit warnings
are grouped by channel and report the affected MIDI span, requested
modifier range, and that both preview and export use the same clamp.

### Pitch changes playback speed

DOOM's Wwise Voice Pitch is resampling, not independent time stretching:

    playback rate = 2 ** (final SnapMap semitones / 12)
    pitched one-shot duration = natural duration / playback rate

The browser consumes the compiler's finalized, clamped rate. Seeking converts elapsed wall time
to the corresponding sample offset, and speaker allocation reserves the pitch-adjusted tail.
Preview and exported timeline therefore agree on pitch, sample speed, and voice reuse.
## Volume algorithm

MIDI velocity is meaningful source data and is converted once:

    velocity dB = round(40 * log10(velocity / 127))
    velocity dB = clamp(velocity dB, -60, 0)
    initial note dB = velocity dB
    current note dB = absolute note override or initial note dB
    requested dB = current note dB + global volume
    SnapMap dB = clamp(requested dB, -60, +20)

Global Volume is the simple mix-level control in the bottom plane. Absolute Note volume is an
exception tool in the note inspector and begins at the velocity-derived level. Neither changes
MIDI velocity. Preview consumes the final
compiler value rather than reimplementing this calculation in JavaScript.

## User experience

### Automatic by default

Users importing an ordinary song should not tune roots or octaves. Automatic and curated
instrument choices resolve sample and pitch without more controls. A stable exact-sound root
also follows MIDI automatically.

Tonal root ambiguity is handled automatically with a channel-centered reference. Clearly
nonmusical analysis preserves natural playback and offers Follow MIDI note in Channel settings.
The UI does not add more tuning sliders or imply that an arbitrary SFX has a real root.

### Channel inspector

Clicking a channel row opens one focused side inspector. Its first setting is Follow MIDI note.
Automatic and curated musical mappings show the setting checked and disabled because following
is intrinsic to their pitch model. Automatic percussion shows it off and disabled because pitch
is encoded by per-key sound selection. Exact sounds make it editable. The normal surface says
only whether the sound follows MIDI or plays naturally; a collapsed Advanced pitch reference is
available for expert correction without exposing detector confidence or formula text. This keeps
a channel-wide choice out of per-note editing.

### Per-note inspector

Clicking a note pauses playback and opens one focused side inspector containing:

- MIDI note;
- resolved sound;
- one Pitch adjustment control;
- one Note volume control initialized from MIDI velocity;
- a clamp notice only when an engine boundary is reached.

The detector's subtraction formula and confidence are deliberately absent. They are backend
diagnostics, not musical decisions a user should have to interpret.

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
Settings version 5 makes note volume an absolute pre-master level; versions 1 through 4 migrate
in memory, with relative volume edits retained in a compatibility field until edited. Every
legacy notes entry keeps its playback result. Sidecars remain keyed by
channel:source-pitch:occurrence, so edits survive retimbre, mute, solo, and root changes.

Source choices and user choices persist. Current detected references are retained as cached
evidence, while legacy automatic detections are revalidated on open. Automatic shifts, final
clamps, audio buffers, and display-only channel focus do not persist.

## Preview and export parity

The parser annotates every note with the same root, offset, velocity dB, final modifier, and mix
state used by map export. The preview manifest has two deliberate views:

- events contains only audible notes that survive conversion preparation and is the transport's
  audio schedule;
- display_events contains every mapped source note, including muted, solo-excluded, and
  polyphony-thinned notes, for truthful piano-roll rendering.

JavaScript applies the manifest playback rate and final volume_db gain. It never chooses
a sample, detects a root, recalculates velocity, or changes mixer inclusion.

## Acceptance criteria

- A per-note Pitch adjustment changes SnapMap playback but never note row, channel, id, or curated
  sample choice.
- Curated families use their available multi-sample palette and residual tuning.
- A trusted exact-sound root follows MIDI automatically.
- Tonal root ambiguity follows a centered relative reference; nonmusical sounds keep natural playback.
- Final pitch and volume clamp at the verified SnapMap limits and report the request.
- Preview and exported Timeline events use the same final modifiers.
- Multiple soloed channels play together; mute overrides solo.
- Muted and solo-excluded notes remain visible but never preview or export.
- Channel focus limits note hit-testing without changing conversion state.
- Versions 1 through 4 load as version 5 and legacy note choices retain their playback.
- The full automated test suite and JavaScript syntax gate pass.

## Validation

- `ruff check .` and `ruff format --check .` pass.
- `node --check src/snapmap_midi/ui/web/app.js` passes.
- `pytest -q` passes with 646 tests and four optional installed-baseline skips.
- The saved-map marker gate reports exactly four skips.
- An isolated `pip wheel` build produces the distributable wheel.
- `git diff --check` passes.

## Explicit non-goals

This design does not claim a root for every game event, infer musicality from a filename prefix,
transpose MIDI source data, add a general note editor, or independently time-stretch pitched
audio. SnapMap/Wwise pitch changes playback speed, and preview plus voice reservation reproduce
that behavior.
