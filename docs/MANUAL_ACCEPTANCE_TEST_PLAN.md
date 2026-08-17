# SnapMap MIDI Manual Acceptance Test Plan

This document covers the features added or changed during the recent track-lane, pitch, voice-allocation, timeline-sharding, and performance work. It is intentionally an acceptance checklist: a feature is not considered game-tested merely because its automated tests pass.

## Test status and scope

- Automated baseline at the time this plan was written: **796 passed, 9 skipped**.
- Automated tests cover application logic and generated data structures.
- They do **not** prove audible pitch behavior, sample-accurate fanout, SnapMap editor compatibility, in-game polyphony, or subjective UI responsiveness.
- Run the tests below against the same build and retain failed exports whenever possible.

Record the build before starting:

| Field | Value |
| --- | --- |
| Date | |
| Git commit | |
| Uncommitted changes present | |
| SnapMap/SnapMap Plus build | |
| Audio output/device | |

Use these result labels throughout:

- `[ ] PASS`
- `[ ] FAIL`
- `[ ] BLOCKED`
- `[ ] NOT RUN`

When comparing sounds, change only one setting at a time. Use headphones and disable spatial/enhancement effects where practical.

## Test assets

The supplied MIDI and probe files are in `examples`:

| Asset | Purpose |
| --- | --- |
| `whole_semitone_pitch.mid` | Whole-semitone pitch sequence |
| `whole_semitone_pitch.mid.snapmap.json` | Settings loaded beside that MIDI |
| `fractional_pitch_ab.mid` | Alternating whole and +50-cent notes |
| `fractional_pitch_ab.mid.snapmap.json` | Settings loaded beside that MIDI |
| `pitch_engine_probe.rawmap.json` | Broad engine pitch behavior survey |
| `pitch_order_probe.rawmap.json` | Pitch/start event ordering |
| `pitch_fraction_probe.rawmap.json` | Fractional `fadePitch` values |
| `pitch_overlap_probe.rawmap.json` | One emitter versus several emitters and shared chords |
| `timeline_sync_probe.rawmap.json` | Listener fanout synchronization and stress test |

The steps below also want a dense real-world MIDI, which this repository does
not ship: a commercial transcription is not ours to redistribute. Supply your
own — a multi-track pop or orchestral arrangement of several hundred notes, so
the voice, polyphony and timeline-size limits are actually under pressure.

The rawmap probe installer replaces the active SnapMap Plus rawmap, but first creates a timestamped backup:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName <probe-name>
```

Allowed probe names are:

- `pitch_engine_probe`
- `pitch_order_probe`
- `pitch_fraction_probe`
- `pitch_overlap_probe`
- `timeline_sync_probe`

Install and test only one rawmap probe at a time. The individual `examples/*_PROBE.md` files contain shorter reference sheets.

## 1. Application startup and regression baseline

1. Start the application with no MIDI loaded.
2. Import a small known-good MIDI.
3. Play, pause, stop, seek, export, and re-import it.
4. Confirm there are no new console errors or visibly broken controls.

Expected:

- `[ ]` The application starts without an exception.
- `[ ]` Import completes and the track lanes appear.
- `[ ]` Play, pause, stop, and seeking work.
- `[ ]` Export completes without an exception.
- `[ ]` Re-importing or loading another MIDI does not retain the previous song's track state incorrectly.

## 2. Track lanes, inspectors, and piano-roll navigation

### Track Settings behavior

1. Single-click a track's gear/settings button.
2. Click it again.
3. Open Track Settings on track A, then open it on track B.
4. Single-click the track label itself while in the lane view.
5. Inspect the controls, then expand and collapse **Advanced track settings**.

Expected:

- `[ ]` First gear click opens that track's settings.
- `[ ]` Second click on the same gear closes it.
- `[ ]` Opening track B closes/replaces track A's inspector; only one inspector is active.
- `[ ]` A single click on a label does not accidentally open settings while in lane view.
- `[ ]` Track Type, Follow MIDI note, Analyze sound, Track Transpose, and Track Volume are visible without expanding anything (with pitch controls appearing when an exact sound is selected).
- `[ ]` Advanced track settings starts collapsed and reveals manual sample calibration, Glide, Voices, Polyphony, Sustain Limit, and Release.
- `[ ]` Closing the Advanced section or the inspector does not reset its values.

### Per-track piano roll

1. Double-click a track label/row.
2. Return to lanes and double-click the track's lane content.
3. While inside track A's piano roll, single-click track B's label.
4. Double-click the active track label again.
5. Open a track roll and press `Esc`.

Expected:

- `[ ]` Double-clicking either the label/row or lane opens that track's piano roll.
- `[ ]` Opening the piano roll does not also open Track Settings.
- `[ ]` A single label click while already in a per-track roll switches directly to that track's roll.
- `[ ]` Double-clicking the active track again exits to track lanes.
- `[ ]` `Esc` exits a piano roll to the track lanes.
- `[ ]` On entry or track switch, the selected track's notes are fitted visibly into the window with little or no manual scrolling.
- `[ ]` Tracks with a very small note range are not zoomed to an unusable extreme.

### All Tracks piano roll

1. Use the footer toggle near Grid to select **All Tracks**.
2. Play and seek in that view.
3. Toggle back to **Track lanes**.
4. Press `Esc` while All Tracks is active.

Expected:

- `[ ]` All notes from all tracks appear in one global piano roll.
- `[ ]` Playback and seeking remain functional.
- `[ ]` The toggle returns to the lane view.
- `[ ]` `Esc` also returns to lanes.

## 3. Zoom, scrolling, playhead, and rendering

Use both a small MIDI and Bitter Sweet Symphony.

### Extreme zoom

1. Increase horizontal zoom to its maximum.
2. Pan from the beginning to the end of the song.
3. Repeat in track lanes, a per-track roll, and All Tracks.

Expected:

- `[ ]` Notes/clips never disappear into an all-white lane view, including beyond the formerly failing approximately 4222% region.
- `[ ]` The grid and notes remain aligned.
- `[ ]` Track lanes show the same faint beat subdivisions and stronger bar lines as the piano roll; changing Grid or Time signature updates both views together.
- `[ ]` The scrollbar reaches both ends and does not jump unexpectedly.

### Playback follow

1. Zoom in enough that the complete song does not fit.
2. Start playback near the beginning.
3. Let the playhead cross several viewport widths.
4. Seek near the end and repeat.

Expected:

- `[ ]` The playhead remains visually continuous.
- `[ ]` Horizontal follow scroll begins smoothly near the intended edge.
- `[ ]` The playhead does not appear to stop around three-quarters of the window and bounce back to the left edge.
- `[ ]` There is no large discontinuous scroll unless the user explicitly seeks.

### Grey timeline bar regression

1. Start and stop playback repeatedly in track-lane view.
2. Resize the window while playing.
3. Change zoom while playing.

Expected:

- `[ ]` No unexplained grey bar appears over the timeline or lanes.
- `[ ]` Only the intended scrollbar, ruler, and playhead are visible.

### Keyboard, scrollbar, and inspector controls

1. Start the app with a song already configured, and press `Space` before clicking anywhere.
2. Focus each slider, checkbox, select, and toolbar button, then press `Space` again.
3. Focus a text or number field and type normally.
4. Click Conversion Settings twice, then open it once more and close it with its X button.
5. In track-lane view, drag the horizontal scrollbar from start to end.

Expected:

- `[ ]` The first `Space` starts playback without a preparatory mouse click.
- `[ ]` `Space` always toggles playback from non-typing controls and does not activate them.
- `[ ]` Text and number fields retain normal keyboard editing.
- `[ ]` Conversion Settings opens and closes from the same toolbar button.
- `[ ]` The lane scrollbar remains visible, aligned with the ruler, and does not cover notes.

### Track Volume

1. Open Track Settings for one track and set Track Volume to -6 dB.
2. Inspect one note on that track and one note on another track.
3. Set an individual note volume, then move Track Volume again.
4. Preview and export the song.

Expected:

- `[ ]` Only the chosen track changes level.
- `[ ]` The note readout shows separate Note, Track, Global, and output contributions.
- `[ ]` Moving Track Volume does not rewrite the individual note-volume value.
- `[ ]` Preview and exported playback use the same final dB result.

## 4. Dense-file UI performance

Load Bitter Sweet Symphony and wait for import/drawing to settle. Perform each action in track lanes and again in All Tracks.

1. Toggle mute on several tracks rapidly.
2. Toggle solo between several tracks.
3. Drag volume, pan, pitch, voice, and other visible sliders continuously.
4. Open and switch between several piano rolls.
5. Zoom, scroll, seek, and resize the window.
6. Play while performing the actions above.
7. While playback continues, change Track Volume, Global Volume, pitch, polyphony, and a sound assignment.

Expected:

- `[ ]` Mute and solo update promptly without multi-second stalls.
- `[ ]` Slider thumbs track the pointer instead of freezing and applying changes much later.
- `[ ]` The All Tracks view remains usable when full, even if it is heavier than a single-track roll.
- `[ ]` Switching tracks does not redraw unrelated controls visibly.
- `[ ]` Playback does not steadily degrade after repeated navigation.
- `[ ]` Editing a control never pauses, restarts, or hard-cuts the transport.
- `[ ]` Already-ringing and look-ahead-scheduled notes finish normally; the updated conversion takes over on subsequent notes.
- `[ ]` A newly selected sound starts after its preview sample is ready without silencing the old performance while it loads.

Record approximate worst delays:

| Action | Lanes | All Tracks |
| --- | ---: | ---: |
| Mute/solo response | | |
| Slider response | | |
| Open/switch roll | | |
| Zoom/scroll response | | |

## 5. Pitch engine primitive probes

These probes isolate engine behavior from MIDI conversion. Test them before diagnosing the analyzer or compiler.

### 5.1 Pitch/start ordering

Install:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName pitch_order_probe
```

Trigger the `pitch-order-probe` switch once. Listen every two seconds:

| Time | Case | Record `C4`, `clean C5`, or `glide/chirp` |
| ---: | --- | --- |
| 0 s | C4 reference | |
| 2 s | Start then pitch at same timestamp | |
| 4 s | Pitch then start at same timestamp | |
| 6 s | Pitch 1 ms after start | |
| 8 s | Pitch 2 ms after start | |
| 10 s | Pitch 5 ms after start | |
| 12 s | Pitch 10 ms after start | |
| 14 s | Pitch 20 ms after start | |
| 16 s | Pitch 50 ms after start | |

Acceptance target:

- `[ ]` The 4-second pitch-before-start case is a clean C5 with no glide.
- `[ ]` The result confirms the production event ordering remains valid in the current engine/editor build.

### 5.2 Fractional pitch/cents

Install:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName pitch_fraction_probe
```

Trigger the switch once. The sequence is C4, `+0.25`, `+0.50`, `+0.75`, `+1.00`, `-0.25`, `-0.50`, `-0.75`, `-1.00`, and `+12.00` semitones, at two-second intervals.

Expected:

- `[ ]` The positive quarter steps rise progressively rather than all rounding to the same pitch.
- `[ ]` The negative quarter steps fall progressively.
- `[ ]` `+1.00` is one semitone above C4.
- `[ ]` `+12.00` is C5.
- `[ ]` No step unexpectedly glides when glide time is zero.

This probe is the direct confirmation that the timeline accepts floating-point pitch values. The UI intentionally displays whole cents rather than raw fractional semitones.

### 5.3 Emitter overlap and chord behavior

Install:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName pitch_overlap_probe
```

Expected cases:

- `[ ]` **A, 0–2 seconds:** two notes on one isolated emitter do not overlap.
- `[ ]` **B, 8–10 seconds:** the same notes on two isolated emitters overlap.
- `[ ]` **C, 16 seconds:** C4, E4, and G4 on one shared automatic/native emitter form a chord.

Interpretation:

- One isolated emitter behaves as one stealable voice.
- Multiple isolated emitters are required for independently pitched overlap.
- A shared automatic/native emitter can still produce several simultaneous native sound events. It is one entity but represents several audible/MIDI voices for polyphony accounting.

### 5.4 Broad engine survey and explicit glide

Install the broad probe only if a regression remains unclear:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName pitch_engine_probe
```

The most important observations are:

- `[ ]` 0 seconds is the C4 reference.
- `[ ]` Equal-time pitch/start variants produce the expected C5 where supported.
- `[ ]` The 8-second generic case intentionally glides from C4 to C5 over 250 ms.
- `[ ]` The Speaker glide case, if retained by the engine, behaves consistently.

This probe is diagnostic; production export currently relies on timeline emitters and pitch-before-start ordering, not a Speaker entity for every note.

## 6. Analyzer and per-track pitch controls

The analyzer decodes the selected audio, examines the waveform/frequencies, estimates fundamentals with a YIN-based detector, and uses spectral checks to reduce octave/harmonic mistakes. It can still be wrong on noisy, transient, inharmonic, or non-musical sounds, so the result remains user-adjustable.

Before pressing Analyze, select a new exact sound and confirm selection itself performs no pitch
analysis, leaves Follow MIDI note off, and plays the sound unchanged. Analysis and manual tuning
must both remain explicit user choices.

Choose at least:

- one clean sustained pitched sound;
- one sound whose known root is not C;
- one short/percussive or noisy sound;
- one ambiguous/multi-layer sound.

For each sound:

1. Assign it to a track.
2. Press **Analyze sound**.
3. Record detected note, MIDI value, confidence, and whether the result sounds correct.
4. Analyze it again and check stability.
5. Manually correct the root when it is wrong.

Expected:

- `[ ]` Selecting an exact sound does not display an analyzing/busy state or call the analyzer.
- `[ ]` A newly selected exact sound defaults to natural playback with Follow MIDI note off.
- `[ ]` A clean tone produces a plausible note and MIDI number.
- `[ ]` Repeated analysis of the same clean file is stable or nearly stable.
- `[ ]` An obviously ambiguous/non-pitched sound is not presented with false high confidence.
- `[ ]` A failed/ambiguous analysis can still be configured manually.
- `[ ]` The analyzer uses the actual sound data, not a filename-only guess.
- `[ ]` Refresh/reanalyze updates the cached result.

### Root, calibration, and transpose

1. Use a sample known to sound at D-sharp.
2. Analyze it and verify the displayed octave as well as pitch class.
3. Press **Play C4 reference** and verify that a clean 261.63-Hz tone continues
   until **Stop C4 reference** is pressed, without changing or stopping the track.
4. Verify **Inferred sample natural note** says D-sharp; this is calibration of the
   unmodified recording, not a direct pitch-up/down control.
5. Play MIDI C with Follow MIDI note enabled. The automatic correction should
   be downward from D-sharp to C.
6. Raise and lower **Track Transpose** by whole semitones. Positive values must
   sound higher and negative values must sound lower.
7. Observe the displayed natural playback pitch after track controls.
8. Export and listen in game.

For a second sound that the analyzer cannot identify:

1. Confirm the UI reports no stable root rather than inventing one.
2. Loop **Play C4 reference**.
3. Adjust **Coarse sample tuning** in whole semitones and then **Sample tuning
   fine adjustment** in whole cents until the sample agrees by ear.
4. Confirm Follow MIDI note turns on and the inferred natural-note readout updates.
5. Play a melody across several notes, then use Track transpose separately.

Expected:

- `[ ]` Note names include sharps correctly: C, C#, D, D#, E, F, F#, G, G#, A, A#, B.
- `[ ]` The reference tone is MIDI 60 / 261.63 Hz, loops until stopped, and then stops cleanly without a click or lingering oscillator.
- `[ ]` The chosen octave naming convention changes labels only; it does not change MIDI values or exported pitch.
- `[ ]` Track Transpose accepts whole semitones in the supported `-24` to `+24` range.
- `[ ]` Raising Inferred sample natural note increases the compensating downward correction for the same MIDI target; it does not act like Track Transpose.
- `[ ]` Raising Track Transpose raises the audible result, and lowering it lowers the audible result.
- `[ ]` Manual coarse sample tuning spans -24 through +24 semitones with direct audible direction.
- `[ ]` Manual sample fine adjustment spans -100 through +100 whole cents.
- `[ ]` Either manual calibration control enables Follow MIDI note and every MIDI note preserves its interval from the calibrated MIDI-60 sample.
- `[ ]` Track transpose remains independent after manual sample calibration.
- `[ ]` Internally, `50` cents exports as half a semitone rather than being rounded to 0 or 1.
- `[ ]` Reanalysis reports the raw detected sample pitch; the separate natural-playback display accounts for calibration and Track transpose.
- `[ ]` A legacy sidecar detune remains audible and visible in the readout, but a new manual calibration clears it.

### Whole-semitone MIDI end-to-end

Import `examples\whole_semitone_pitch.mid`. Confirm its sidecar loads, preview it, export it, then play the exported map in game.

Expected sequence from a C4 piano sample:

| MIDI note | Expected pitch offset |
| --- | ---: |
| C4 | 0 |
| D4 | +2 |
| E4 | +4 |
| F4 | +5 |
| G4 | +7 |
| A4 | +9 |
| B4 | +11 |
| C5 | +12 |

- `[ ]` Preview follows the sequence.
- `[ ]` In-game export follows the same sequence.
- `[ ]` Notes begin already pitched; they do not glide from C4 when glide is zero.

### Fractional MIDI A/B end-to-end

Keep `fractional_pitch_ab.mid.snapmap.json` beside `fractional_pitch_ab.mid`, import the MIDI, and verify that the sidecar is detected automatically.

- `[ ]` The A notes use whole-semitone pitch.
- `[ ]` The alternating B notes are audibly 50 cents higher.
- `[ ]` Preview and in-game export agree.
- `[ ]` The rawmap contains floating-point pitch values for the B notes.
- `[ ]` No extra Speaker entities are created merely because cents are enabled.

## 7. Track glide

Use an exact/fixed sample track, not an automatic instrument whose notes are separate pre-tuned samples.

1. Set Track Voices to 1.
2. Set Track Glide to 0 ms and play a connected melody.
3. Test short, medium, and obvious glide values such as 10, 100, and 500 ms.
4. Repeat with overlapping notes and with Track Voices greater than 1.
5. Save, reopen, export, and test in game.

Expected:

- `[ ]` The default is 0 ms and produces no glide.
- `[ ]` Increasing the value makes the transition progressively longer.
- `[ ]` A one-voice track behaves like monophonic portamento and steals/reuses its voice predictably.
- `[ ]` Multiple voices do not all glide from an unrelated prior note.
- `[ ]` The exported map matches preview closely.
- `[ ]` The glide value persists in the sidecar.

## 8. Global and per-track polyphony/voice limits

These controls are intentionally different:

- **Global Polyphony** limits admitted, currently held MIDI notes across the whole song.
- **Track Polyphony** limits admitted, currently held MIDI notes on one track.
- **Global Voices** limits the pool of isolated/independently pitched emitters.
- **Track Voices** limits one track's share of that isolated emitter pool and can steal existing tails.
- One shared automatic emitter may play a chord, but that chord still counts as multiple notes for polyphony.
- Ringing sample tails do not count as held MIDI notes for Global Polyphony.

### Defaults and persistence

1. Load a fresh MIDI with no sidecar.
2. Open Conversion Settings and Track Settings.
3. Save/reopen after changing every limit.

Expected:

- `[ ]` Global Voices defaults to 32 and is labelled **Global Voices**.
- `[ ]` Global Polyphony defaults to 32.
- `[ ]` Track Voices and Track Polyphony controls are present per track.
- `[ ]` Default Track Polyphony is available as an optional override and clearly indicates whether it is enabled.
- `[ ]` Values and enable/disable states persist.

Design check requiring an explicit product decision:

- `[ ]` Decide whether **Enable default limit** for Default Track Polyphony should be checked for a new song. The current behavior must be compared with the intended default rather than assumed correct.

### Visual polyphony rejection

Use a sustained chord with more notes than the selected limit.

1. Set Track Polyphony to 2 and play a four-note chord.
2. Disable that override and set Global Polyphony to 2.
3. Repeat with notes on several tracks at the same onset.
4. Add notes that begin while earlier notes are still held.

Expected:

- `[ ]` Only the allowed number of notes sound.
- `[ ]` Refused notes are visibly hollow in the piano roll.
- `[ ]` Same-onset selection follows the intended highest-note priority.
- `[ ]` Already-admitted notes keep their musical duration; reducing polyphony does not randomly chop them.
- `[ ]` Later notes use only remaining held-note slots.
- `[ ]` Global Polyphony counts notes across shared automatic and isolated fixed-sample tracks together.
- `[ ]` A C-E-G chord on one shared emitter consumes three polyphony slots, not one.

### Voices and voice stealing

1. On a fixed-sample track, set Track Voices to 1 and play overlapping notes.
2. Increase it to 2, then 4.
3. Use two or more tracks with a low Global Voices value.
4. Compare a shared automatic instrument chord with independently pitched fixed-sample notes.

Expected:

- `[ ]` Track Voices 1 is monophonic and later notes steal the active isolated voice/tail.
- `[ ]` Higher values allow the corresponding additional isolated overlap.
- `[ ]` Global Voices caps isolated emitters song-wide.
- `[ ]` Mute/solo and note selection remain deterministic rather than apparently random.
- `[ ]` Shared automatic/native chords are not incorrectly treated as only one audible note by Global Polyphony.

## 9. Sustain, release, and hard stop

Voice count and note duration are separate. Use Sustain Limit to shorten musical notes deliberately; do not expect lowering Voices alone to shorten every note.

1. Test with all sustain-limit overrides disabled.
2. Enable the global/default track sustain limit.
3. Override it on one track with a shorter and then longer value.
4. Test **Default Track Release** at note end.
5. Enable **Track Release** on one sustained/looping track and give it a
   visibly different value from the default.
6. Test Hard Stop on the same sound.
7. Use a long-ringing sample and closely spaced notes.

Expected:

- `[ ]` With limits off, MIDI duration is preserved subject to voice stealing.
- `[ ]` Track override takes precedence over family/global default.
- `[ ]` Sustain Limit changes note duration independently of Voices and Polyphony.
- `[ ]` Release starts at MIDI note-off, not at note-on.
- `[ ]` A Track Release override wins over Default Track Release for that track.
- `[ ]` Release fades sustained or looping sounds to silence over the configured time.
- `[ ]` Ordinary decaying one-shots and drums keep their natural envelope rather than receiving an artificial release fade.
- `[ ]` Hard Stop stops the sound at note end.
- `[ ]` The bass duration ceiling still acts as an additional ceiling where enabled.

## 10. Drums and one-shots

Use a MIDI with channel-10 drums and choose several curated drum sounds, including sounds with audible tails.

1. Play two different drum notes close together.
2. Repeat the same note rapidly.
3. Play a drum note under a melodic chord with low and high Global Polyphony.
4. Inspect the drum picker for looping assets.
5. Test per-key assignment persistence, mute, solo, preview, and export.

Expected:

- `[ ]` Drum one-shots overlap naturally and their tails are not cut solely because the next drum hit starts.
- `[ ]` Global Polyphony counts held drum MIDI events, not the full acoustic tail after note-off.
- `[ ]` Track Sustain Limit does not unexpectedly gate ordinary fire-and-forget drum one-shots.
- `[ ]` Curated picker choices exclude known looping sounds.
- `[ ]` Per-key sound assignments persist and export correctly.
- `[ ]` Mute and solo affect drum tracks correctly.

Safety note: a hand-edited sidecar can still name an arbitrary `Play_` event. Do not assume every arbitrary sound is a safe non-looping drum sample.

## 11. Parked timeline sharding and listener fanout probe

Automatic sharding is currently disabled by project decision. Production exports use one master
Timeline and one listener target. The fanout probe remains available only to preserve the research
and to support a future decision to reactivate sharding.

### Synchronization probe

Install:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName timeline_sync_probe
```

Trigger the switch once and compare:

| Time | Case |
| ---: | --- |
| 0 s | Reference C-E-G chord from one scheduler |
| 4 s | Three-target listener fanout chord |
| 8 s | Reference doubled hi-hat |
| 12 s | 33-target production-size fanout |
| 16 s | 128-target stress fanout |

Expected:

- `[ ]` The 4-second chord is simultaneous, not an audible arpeggio.
- `[ ]` The 12-second case has no flam, echo, combing, or obvious phase smear compared with the 8-second reference.
- `[ ]` The 16-second stress case remains simultaneous or its deviation is measured and documented.

For a more objective check, record lossless 48 kHz WAV. At 48 kHz, 48 samples are 1 ms and 480 samples are 10 ms. Compare transient start samples rather than relying only on perception.

### Real large-song single-Timeline export

1. Import Bitter Sweet Symphony.
2. Export it with the current settings.
3. Record the serialized size of the master Timeline.
4. Open the map and attempt to open its master Timeline in the editor.
5. Play the beginning, several middle locations, the final section, and dense transitions.
6. Compare tracks that should begin at the exact same MIDI time.

Expected:

- `[ ]` Export succeeds without exceeding the approximately 1.08 MB per-component buffer ceiling.
- `[ ]` Export reports one activated Timeline/listener target.
- `[ ]` No event group is moved into an independently activated shard.
- `[ ]` If the master exceeds the editor buffer, the application warns that it will play but may not open for editing.
- `[ ]` One listener activation starts the master Timeline.
- `[ ]` The start, middle, and end of the complete song are present—no dropped late events or tracks.
- `[ ]` Simultaneous notes within the master remain audibly simultaneous.
- `[ ]` Export does not create one Speaker entity per note or otherwise explode entity count unnecessarily.

The earlier 33-shard observation is historical only. Sharding is currently disabled.

## 12. Exported entity and channel behavior

Inspect one small fixed-sample export and one automatic-instrument export, then verify both in game.

Expected:

- `[ ]` The interactive display name exactly matches the imported MIDI filename, not a prior probe or sidecar name.
- `[ ]` The master Unknown is 64 units to the interactive's right and every auxiliary Unknown follows at 32-unit intervals without crossing through the interactive.
- `[ ]` Independently pitched fixed samples receive the required isolated emitters based on voice demand, not one entity for every note.
- `[ ]` Automatic/native instruments can use shared timeline emitters where the engine permits simultaneous native events.
- `[ ]` Pitch and start events target compatible sound channels.
- `[ ]` Pitch is scheduled before start at the same timeline time for zero-glide notes.
- `[ ]` A nonzero glide is the only case that intentionally ramps after note start.
- `[ ]` There are no redundant Speakers all playing `piano_C4` unless a specific allocation setting actually requires separate emitters.
- `[ ]` The first note and every later pitch change sound correct in game, not merely in application preview.

## 13. Sidecar loading, saving, and migration

1. Import a MIDI with its exact matching `.mid.snapmap.json` file beside it.
2. Change sound selection, detected/manual root, sample fine adjustment, transpose, glide,
   voices, polyphony, sustain, release, volume, mute, and solo.
3. Do **not** export. Close the application, reopen it, and import the MIDI again.
4. Confirm the edits returned, make one more edit, then export and reopen once more.
5. Move or rename only the sidecar and import again.
6. If available, open an older sidecar created before the recent settings-version changes.

Expected:

- `[ ]` An exact-name adjacent sidecar auto-loads.
- `[ ]` Every successful settings edit updates the adjacent sidecar without requiring Export.
- `[ ]` All current per-track and global settings restore correctly.
- `[ ]` Removing/renaming the sidecar produces clean defaults rather than partially retained prior-song state.
- `[ ]` Older supported sidecars migrate without crashing or silently corrupting track assignments.
- `[ ]` Export does not require manually importing a JSON sidecar through the MIDI file chooser.

## 14. Features discussed but not yet acceptance-ready

Do not report these as regressions in the current build unless implementation work was subsequently added:

- Full attack/decay/sustain-level/release envelope controls for every sound.
- A managed Natural/ADSR mode selector.
- Drum choke groups such as closed hi-hat stopping open hi-hat.
- Guaranteed safe handling of arbitrary looping events manually inserted into a drum sidecar.
- Per-key drum gate/release envelopes.

The current Release/Hard Stop and Sustain Limit behavior should still be tested as described above; those are not equivalent to a complete ADSR envelope.

## 15. Final acceptance matrix

| Area | Result | Notes/evidence |
| --- | --- | --- |
| Startup/import/export | | |
| Track settings interaction | | |
| Per-track piano rolls | | |
| All Tracks piano roll | | |
| Zoom/playhead/grey-bar fixes | | |
| Dense-file performance | | |
| Pitch ordering | | |
| Fractional cents | | |
| Analyzer accuracy/fallback | | |
| Whole-semitone export | | |
| Track glide | | |
| Global/track polyphony | | |
| Global/track voices | | |
| Sustain/release/hard stop | | |
| Drums/one-shots | | |
| Listener fanout synchronization | | |
| Timeline sharding/editor load | | |
| Sidecar persistence/migration | | |

## Failure report template

Copy this block for every failure:

```text
Test section and step:
Build/commit:
MIDI or probe:
Track and sound event:
Conversion/track settings:
Expected:
Observed:
Preview, editor, or in-game:
Reproducible every time? yes/no
Exported rawmap retained? yes/no
Screenshot/audio/video path:
Console or export error:
```

For audio failures, a short lossless recording plus the exported rawmap is substantially more useful than a description alone. For UI performance failures, include the MIDI, current view, zoom percentage, and approximate delay.
