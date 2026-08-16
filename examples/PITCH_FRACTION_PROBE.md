# Fractional pitch probe

This uses the proven clean ordering: `fadePitch` appears immediately before
`startSoundShader` in the saved equal-time event array. There is no delay and
`over` is zero.

| Time | Pitch |
|---:|---:|
| 0 s | 0 (C4 reference) |
| 2 s | +0.25 semitone (+25 cents) |
| 4 s | +0.50 semitone (+50 cents) |
| 6 s | +0.75 semitone (+75 cents) |
| 8 s | +1.00 semitone (C-sharp 4) |
| 10 s | -0.25 semitone (-25 cents) |
| 12 s | -0.50 semitone (-50 cents) |
| 14 s | -0.75 semitone (-75 cents) |
| 16 s | -1.00 semitone (B3) |
| 18 s | +12.00 semitones (C5 control) |

The first five notes should rise smoothly in quarter-semitone steps. The next
four should descend below C4. The final note confirms the already-proven whole
octave behavior.

Install it from the repository root:

```powershell
python tools\create_pitch_fraction_probe.py
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName pitch_fraction_probe
```
