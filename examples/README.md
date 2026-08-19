# Fractional pitch A/B test

Open `fractional_pitch_ab.mid` in the workstation. Its sidecar assigns the same
C4 piano sample to both tracks:

- **A - Whole semitones** plays on beats 1, 3, 5, and so on with whole-number
  `fadePitch` values.
- **B - Plus 50 cents** answers on beats 2, 4, 6, and so on with the same MIDI
  melody plus `50` cents, producing `.5`-semitone `fadePitch` values.

The alternating identical pitches make the half-semitone difference audible.
Change the second track's **Fine tune** setting to compare smaller cent values.
The MIDI is reproducible with `python tools/create_fractional_pitch_test.py`.

## Whole-semitone control

`whole_semitone_pitch.mid` is the integer-only control. It plays one C4 piano
sample as C4, D4, E4, F4, G4, A4, B4, and C5. Its sidecar uses one global voice
and velocity 127, so the exported Timeline contains one Speaker and no
`fadeSound` events. The expected nonzero `fadePitch` targets are `2`, `4`, `5`,
`7`, `9`, `11`, and `12`.

Regenerate it with `python tools/create_whole_pitch_test.py`.
