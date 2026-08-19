# In-game pitch engine probe

`pitch_engine_probe.rawmap.json` is a finished map, not a MIDI file. Copy it to
SnapMap Plus's loader location as `rawmap.json`, load the map, and use the
switch named **pitch-engine-probe** once.

From the repository root, this helper backs up the current loader map and
installs the probe:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_pitch_engine_probe.ps1
```

The backup is written beside `rawmap.json` with a timestamp in its filename.

The probe plays Piano C4 once every two seconds. Case 0 is the unchanged C4
reference. Every other case requests `+12`, so a working case sounds exactly
one octave higher (C5). Case 4 and case 7 should audibly glide upward for a
quarter second if their pitch route works.

| Time | Case | Expected when working |
|---:|---|---|
| 0 s | Generic entity, MUSIC1 start, no pitch | C4 reference |
| 2 s | Generic entity, MUSIC1 start, ANY pitch, same time | C5 |
| 4 s | Generic entity, MUSIC1 start, ANY pitch after 50 ms | C5 |
| 6 s | Generic entity, MUSIC1 start and MUSIC1 pitch, same time | C5 |
| 8 s | Generic entity, MUSIC1 pitch after 50 ms, over 0.25 s | C4-to-C5 glide |
| 10 s | Generic entity, ANY pitch 50 ms before MUSIC1 start | C5 |
| 12 s | Speaker, MUSIC1 start, ANY pitch, same time | C5 |
| 14 s | Speaker, MUSIC1 pitch after 50 ms, over 0.25 s | C4-to-C5 glide |
| 16 s | Generic entity, ANY start and ANY pitch, same time | C5 |

Report which case numbers, if any, sound different from case 0. Also report
whether the two glide cases change pitch gradually or stay at C4.

Regenerate the file with:

```powershell
python tools\create_pitch_engine_probe.py
```
