# Pitched-tail overlap probe

This determines whether independently pitched notes need separate generic
emitters. It also verifies that automatic instruments can keep using their
already-tuned shaders on one shared emitter.

## A — one emitter

- 0 s: Piano C4 sample pitched down to C3.
- 1 s: The same emitter starts the sample pitched up to C5.

Report whether the low C3 tail stops abruptly when C5 begins or continues
underneath it.

## B — two emitters

- 8 s: Piano C4 sample pitched down to C3.
- 9 s: A second emitter starts the sample pitched up to C5.

The low C3 should continue underneath C5. This is the comparison for test A.

## C — automatic, already-tuned shaders

- 16 s: Native `play_pianoc4`, `play_pianoe4`, and `play_pianog4` start at
  exactly the same time on one shared generic emitter.

Report whether you hear the full C-major chord (C, E, and G simultaneously) or
only one of its notes. These starts use `SND_CHANNEL_ANY` and no `fadePitch`,
matching the efficient automatic-instrument path.

Install it from the repository root:

```powershell
python tools\create_pitch_overlap_probe.py
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName pitch_overlap_probe
```
