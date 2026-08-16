# Pitch ordering probe

This probe tests whether the proven Timeline pitch route can avoid an audible
C4 lead-in. Every case requests C5 (`+12`) from the same Piano C4 sample.

| Time | Case |
|---:|---|
| 0 s | C4 reference |
| 2 s | Equal time, event array contains start then pitch |
| 4 s | Equal time, event array contains pitch then start |
| 6 s | Pitch 1 ms after start |
| 8 s | Pitch 2 ms after start |
| 10 s | Pitch 5 ms after start |
| 12 s | Pitch 10 ms after start |
| 14 s | Pitch 20 ms after start |
| 16 s | Pitch 50 ms after start—the previously proven route |

For each case, report **C4**, **clean C5**, or **audible glide/chirp**. The first
clean C5 case is the production scheduling rule. If the reversed equal-time
case works, the Timeline queue reverses ties. If a 1–5 ms delay works cleanly,
the initial unpitched interval is short enough to stay inside one audio update.

Install it from the repository root:

```powershell
python tools\create_pitch_order_probe.py
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1 -ProbeName pitch_order_probe
```
