# Timeline fanout synchronization probe

This map tests whether one listener starts several Timeline targets on the same
engine/audio clock, or whether target order introduces a delay.

Install it with:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName timeline_sync_probe
```

Activate the `timeline-sync-probe` switch once, then listen for five tests:

1. **0 seconds — reference chord:** one Timeline scheduler starts C4, E4, and
   G4 on three emitters.
2. **4 seconds — three-target fanout chord:** the listener starts three
   Timeline shards, one note per shard. It should sound like the same single
   chord, not a quick arpeggio.
3. **8 seconds — reference doubled transient:** one Timeline scheduler starts
   the same hi-hat on two emitters at the same scheduled time.
4. **12 seconds — 33-target production fanout:** the first and last targets
   start that same hi-hat; 31 empty targets sit between them. This matches the
   shard count produced by the large Bittersweet Symphony test conversion.
5. **16 seconds — 128-target stress fanout:** the first and last targets start
   the hi-hat; 126 empty Timeline targets are between them.

Compare 8 seconds with both 12 and 16 seconds. If either fanout sound becomes a
flam, echo, or noticeably different comb/phase sound, the listener is adding
first-to-last target skew. The 12-second result is the important production
case; the 16-second result deliberately exceeds the current song's needs.

A lossless recording is more useful than listening alone. At 48 kHz, 48
samples equal 1 ms and 480 samples equal 10 ms. Record the whole run as WAV if
possible; the two hi-hat onsets can then be compared at sample resolution.

To regenerate the probe:

```powershell
python tools\create_timeline_sync_probe.py
```
