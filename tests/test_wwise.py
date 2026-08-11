"""The soundbank reader, against banks this file builds rather than a game.

CI has no game install and neither does most of anyone's machine, so the format
code is tested against synthesised banks: a `BKHD` + `DIDX` + `DATA` + `HIRC`
assembled here as bytes, and ADPCM frames whose output is worked out by hand
below. That is not a compromise. Four of the traps in this format produce audio
that plays -- too long, or clicking, or the wrong nibble order -- and a test
that only asserted "it decoded something" would pass on every one of them. A
hand-computed vector is the only thing that catches them.

The handful of tests that need the real game carry `gamedata` and take an
install from `locate`, skipping when there is not one.
"""

from __future__ import annotations

import ast
import struct
from pathlib import Path

import pytest

from snapmap_midi.audio import locate, wwise

# ---- building a soundbank out of nothing ----


def chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack("<I", len(payload)) + payload


def hirc_object(kind: int, payload: bytes) -> bytes:
    """One HIRC record: type byte, size, then `size` bytes STARTING at the id.

    The size counting the id is the part that is easy to get wrong, and getting
    it wrong walks the object list off by four per record until it reads a
    length of several gigabytes.
    """
    return bytes([kind]) + struct.pack("<I", len(payload)) + payload


def sound_payload(object_id: int, media_id: int, stream_type: int = 0) -> bytes:
    return (
        struct.pack("<I", object_id)
        + struct.pack("<I", 0x00040001)  # plugin id: the built-in source
        + bytes([stream_type])
        + struct.pack("<I", media_id)
        + b"\x00" * 8
    )


def action_payload(object_id: int, target_id: int) -> bytes:
    return struct.pack("<I", object_id) + b"\x00\x04" + struct.pack("<I", target_id) + b"\x00" * 4


def event_payload(object_id: int, action_ids) -> bytes:
    return (
        struct.pack("<I", object_id)
        + struct.pack("<I", len(action_ids))
        + b"".join(struct.pack("<I", a) for a in action_ids)
    )


def container_payload(object_id: int, child_ids) -> bytes:
    return (
        struct.pack("<I", object_id)
        + struct.pack("<I", len(child_ids))
        + b"".join(struct.pack("<I", c) for c in child_ids)
    )


def build_bank(chains=(), media=None, version: int = wwise.BANK_VERSION, container=False) -> bytes:
    """A soundbank holding one event chain per (name, media id) pair.

    `container` routes each action through a random container holding the sound
    instead of naming the sound directly, which is how most real events are
    built and is the one path `_children` covers.
    """
    objects, ids = [], 0x40000000
    for index, (name, media_id) in enumerate(chains):
        sound_id = ids + index * 4
        objects.append(hirc_object(2, sound_payload(sound_id, media_id)))
        target = sound_id
        if container:
            target = sound_id + 1
            objects.append(hirc_object(5, container_payload(target, [sound_id])))
        action_id = sound_id + 2
        objects.append(hirc_object(3, action_payload(action_id, target)))
        objects.append(hirc_object(4, event_payload(wwise.fnv1_32(name), [action_id])))

    body = chunk(b"BKHD", struct.pack("<IIII", version, 0xABCD1234, 0, 0))
    if media:
        index_chunk, data = b"", b""
        for media_id, blob in media.items():
            index_chunk += struct.pack("<III", media_id, len(data), len(blob))
            data += blob
        body += chunk(b"DIDX", index_chunk) + chunk(b"DATA", data)
    body += chunk(b"HIRC", struct.pack("<I", len(objects)) + b"".join(objects))
    return body


def build_pack(entries) -> bytes:
    """A `.pck` holding (media id, block size, payload) rows.

    Block size is a real field and not a formality: the stored offset is a
    block INDEX, so a reader that forgets to scale it reads the wrong part of
    the file. Pass 1 for an unscaled row and something larger to pin the
    multiply.
    """
    language, banks, externals = struct.pack("<I", 0), struct.pack("<I", 0), struct.pack("<I", 0)
    table_size = 4 + len(entries) * 20
    header_size = 20 + len(language) + len(banks) + table_size + len(externals)
    body_start = 8 + header_size

    rows, data = b"", b""
    for media_id, block, payload in entries:
        offset = body_start + len(data)
        padding = (-offset) % block if block else 0
        data += b"\x00" * padding
        offset += padding
        start = offset // block if block else offset
        rows += struct.pack("<IIIII", media_id, block, len(payload), start, 0)
        data += payload
    header = struct.pack("<IIIII", 1, len(language), len(banks), table_size, len(externals))
    return (
        b"AKPK"
        + struct.pack("<I", header_size)
        + header
        + language
        + banks
        + struct.pack("<I", len(entries))
        + rows
        + externals
        + data
    )


def build_event_catalog(records) -> bytes:
    """A generated soundbanksinfo.events file from dictionaries."""
    body = struct.pack(">I", len(records))
    for record in records:
        name = record["name"]
        body += struct.pack(">I", record.get("id", wwise.fnv1_32(name)))
        for field in ("name", "path", "bus", "environment"):
            encoded = record.get(field, "").encode("utf-8")
            body += struct.pack("<I", len(encoded)) + encoded
        trailer = bytearray(wwise.EVENT_RECORD_TRAILER_BYTES)
        trailer[0] = 1 if record.get("looping") else 0
        trailer[5:13] = struct.pack(
            ">ff",
            float(record.get("duration_min", 0.0)),
            float(record.get("duration_max", 0.0)),
        )
        body += trailer
    return body + b"generated-footer"


def frame(predictor: int = 0, step_index: int = 0, nibbles=()) -> bytes:
    """One 36-byte ADPCM frame: predictor, step index, pad, then 32 body bytes.

    Nibbles are laid low-then-high within each byte, which is the order the
    decoder reads them in and the opposite of the one the standard library's
    retired `audioop` used.
    """
    body = bytearray(32)
    for i, code in enumerate(nibbles):
        if i & 1:
            body[i >> 1] |= (code & 0xF) << 4
        else:
            body[i >> 1] |= code & 0xF
    return struct.pack("<hBB", predictor, step_index, 0) + bytes(body)


def wem(frames: bytes, channels: int = 1, rate: int = 22050) -> bytes:
    align = wwise.FRAME_BYTES * channels
    fmt = struct.pack(
        "<HHIIHH", wwise.WWISE_IMA_FORMAT_TAG, channels, rate, rate * align // 64, align, 4
    )
    body = chunk(b"fmt ", fmt) + chunk(b"data", frames)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def write_install(root, banks=(), packs=(), events=None) -> Path:
    """A directory shaped like an install, holding the given bank/pack bytes."""
    folder = Path(root) / wwise.SOUND_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    for index, blob in enumerate(banks):
        (folder / ("synth%02d.bnk" % index)).write_bytes(blob)
    for index, blob in enumerate(packs):
        (folder / ("synth%02d.pck" % index)).write_bytes(blob)
    if events is not None:
        (folder / wwise.EVENT_CATALOG_NAME).write_bytes(events)
    return Path(root)


# ---- named event catalog ----


def test_the_event_catalog_preserves_names_hierarchy_and_mixed_endianness(tmp_path):
    path = tmp_path / wwise.EVENT_CATALOG_NAME
    path.write_bytes(
        build_event_catalog(
            [
                {
                    "id": 0xF0123456,
                    "name": "Play_Test_Loop",
                    "path": "doom_test/folder/",
                    "bus": "SFX_Test",
                    "environment": "amb_quiet_300_1200",
                    "looping": True,
                    "duration_min": 1.25,
                    "duration_max": 2.5,
                }
            ]
        )
    )

    assert wwise.parse_event_catalog(path) == (
        wwise.SoundEvent(
            0xF0123456,
            "Play_Test_Loop",
            "doom_test/folder/",
            "SFX_Test",
            "amb_quiet_300_1200",
            True,
            1.25,
            2.5,
        ),
    )


def test_a_truncated_event_catalog_is_refused_by_record_number(tmp_path):
    path = tmp_path / wwise.EVENT_CATALOG_NAME
    path.write_bytes(struct.pack(">I", 1) + b"\x00\x01")
    with pytest.raises(ValueError, match="record 0"):
        wwise.parse_event_catalog(path)


def test_the_xml_overlay_marks_infinite_and_mixed_events_as_looping(tmp_path):
    path = tmp_path / wwise.EVENT_XML_NAME
    path.write_text(
        '<Root><Event Name="Play_One" DurationType="OneShot"/>'
        '<Event Name="Play_Mixed" DurationType="Mixed"/>'
        '<Event Name="Play_Loop" DurationType="Infinite"/></Root>',
        encoding="utf-8",
    )
    assert wwise.parse_looping_event_names(path) == {
        "play_mixed",
        "play_loop",
    }


# ---- what it is allowed to depend on ----


def test_the_format_reader_imports_nothing_internal():
    """This module is a soundbank reader that happens to live here.

    The layering test one directory up only forbids reaching UPWARD, which
    would let this import `paths` or `sound` quite legally -- and one
    convenience import is all it takes to turn promoting this out of the
    package from a directory move into an untangling. So the rule here is
    stricter than the rule for the layer it sits in, and it is checked here
    because this is the only file it applies to.
    """
    tree = ast.parse(Path(wwise.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert not node.level, "relative import in a module that must stand alone"
            imported.add(node.module or "")
    assert not [name for name in imported if name.startswith("snapmap_midi")], sorted(imported)


# ---- name hashing ----


def test_the_hash_is_fnv1_and_not_fnv1a():
    """The anchor value, and the mistake it exists to catch.

    FNV-1 multiplies then xors; FNV-1a xors then multiplies. Both are 32-bit,
    both are one line, and both look right. Written the wrong way round, not a
    single sound in the palette resolves -- so the failure is loud, but only if
    you know to suspect it.
    """
    assert wwise.fnv1_32("play_pianoc4") == 260642272

    def fnv1a(name):
        digest = 2166136261
        for byte in name.encode("utf-8"):
            digest = ((digest ^ byte) * 16777619) & 0xFFFFFFFF
        return digest

    assert fnv1a("play_pianoc4") != wwise.fnv1_32("play_pianoc4")


def test_the_hash_lowercases_its_input():
    """Wwise hashes the lowercased name, and the palette is not consistently
    cased. Skipping the fold loses every sound whose declaration has a capital."""
    assert wwise.fnv1_32("Play_PianoC4") == wwise.fnv1_32("play_pianoc4")


def test_the_hash_stays_inside_32_bits():
    for name in ("", "a", "play_violindb6", "x" * 200):
        assert 0 <= wwise.fnv1_32(name) <= 0xFFFFFFFF


# ---- the decoder ----


def test_a_frame_yields_64_samples_not_65():
    """The trap that costs 1.56% and a click per frame.

    A frame is a header sample plus 63 decoded nibbles. Consuming all 64
    nibbles gives 65 samples: the file runs long, every frame boundary gets a
    discontinuity, and the pitch sits slightly flat against the written rate.
    It sounds like a bad rip, which is why it survives a listen.
    """
    out = wwise.decode_wwise_ima(frame(), 1, wwise.FRAME_BYTES)
    assert len(out) == 1
    assert len(out[0]) == 64
    assert wwise.SAMPLES_PER_FRAME == 64


def test_the_last_nibble_is_padding():
    """The direct form of the same trap: nibble 63 must not reach the output."""
    nibbles = [0] * 64
    quiet = wwise.decode_wwise_ima(frame(nibbles=nibbles), 1, wwise.FRAME_BYTES)
    nibbles[63] = 0xF
    loud = wwise.decode_wwise_ima(frame(nibbles=nibbles), 1, wwise.FRAME_BYTES)
    assert quiet == loud


def test_the_hand_computed_vector():
    """Worked out by hand from the step table, with predictor 0 and index 0.

        code 1 : step 7,  delta ((1*2+1)*7)>>3 = 2   -> 2,   index -1 -> 0
        code 9 : step 7,  delta 2, sign bit set      -> 0,   index -1 -> 0
        code 4 : step 7,  delta ((4*2+1)*7)>>3 = 7   -> 7,   index +2 -> 2
        code 7 : step 9,  delta ((7*2+1)*9)>>3 = 16  -> 23,  index +8 -> 10

    The header predictor is emitted first, so the run starts with the 0 it
    carries and not with the first decoded sample.
    """
    out = wwise.decode_wwise_ima(frame(nibbles=[1, 9, 4, 7]), 1, wwise.FRAME_BYTES)
    assert out[0][:5] == [0, 2, 0, 7, 23]


def test_the_delta_is_the_multiply_form_not_the_accumulate_form():
    """The two forms agree on most codes and disagree on the small ones.

    The accumulate form -- `step>>3`, then conditionally add `step`, `step>>1`,
    `step>>2` -- loses the low bits to three separate truncations. At code 1
    and step 7 it yields 1 where the multiply form yields 2. Half a step per
    sample integrates into roughness on sustained tones and into nothing at all
    on a drum hit, so it passes any spot check that is not this one.
    """
    out = wwise.decode_wwise_ima(frame(nibbles=[1]), 1, wwise.FRAME_BYTES)
    step = 7
    accumulate = (step >> 3) + (step if 1 & 4 else 0) + (step >> 1 if 1 & 2 else 0)
    accumulate += step >> 2 if 1 & 1 else 0
    assert accumulate == 1
    assert out[0][1] == 2, "the accumulate form would give %d" % accumulate


def test_the_low_nibble_comes_first():
    """One byte, two different codes, in the order the decoder must read them."""
    packed = wwise.decode_wwise_ima(frame(nibbles=[1, 4]), 1, wwise.FRAME_BYTES)
    assert packed[0][:3] == [0, 2, 9]  # 0, then code 1 (+2), then code 4 (+7)


def test_the_predictor_saturates():
    """A run of maximum positive codes must clip at the int16 ceiling rather
    than wrap, which would turn a loud transient into an inverted one."""
    out = wwise.decode_wwise_ima(frame(predictor=30000, nibbles=[7] * 63), 1, wwise.FRAME_BYTES)
    assert max(out[0]) == 32767
    assert min(out[0]) >= -32768


def test_a_wild_step_index_is_clamped():
    """The header byte can hold anything; the ladder has 89 rungs."""
    out = wwise.decode_wwise_ima(frame(step_index=200, nibbles=[4]), 1, wwise.FRAME_BYTES)
    assert len(out[0]) == 64


def test_multichannel_clusters_whole_frames():
    """Not MS-IMA's 4-byte word interleave.

    Read as interleaved words, channel 1's header would come out of channel
    0's first body bytes -- zero here -- and the result would still be two
    channels of the right length and duration. Asserting the second channel's
    own predictor is what separates the two readings.
    """
    block = frame(predictor=1000) + frame(predictor=-1000)
    out = wwise.decode_wwise_ima(block, 2, wwise.FRAME_BYTES * 2)
    assert len(out) == 2
    assert out[0][0] == 1000
    assert out[1][0] == -1000
    assert len(out[0]) == len(out[1]) == 64


def test_an_unexpected_block_align_is_refused():
    """36 bytes per channel per frame is the whole layout assumption. A file
    that disagrees would decode into noise, so it stops instead."""
    with pytest.raises(ValueError):
        wwise.decode_wwise_ima(frame(), 1, 512)


# ---- containers ----


def test_a_bank_of_the_wrong_version_is_refused(tmp_path):
    """Loud, because the alternative is silent. A later generator moved chunk
    payloads around; these offsets would still parse and still produce ids."""
    path = tmp_path / "future.bnk"
    path.write_bytes(build_bank([("play_x", 1)], version=128))
    with pytest.raises(wwise.UnsupportedBankVersionError) as caught:
        wwise.parse_bnk(path)
    assert "128" in str(caught.value)


def test_a_bank_of_the_measured_version_parses(tmp_path):
    path = tmp_path / "ok.bnk"
    path.write_bytes(build_bank([("play_x", 77)], media={77: b"payload"}))
    objects, media = wwise.parse_bnk(path)
    assert wwise.fnv1_32("play_x") in objects
    assert media[77][1] == len(b"payload")


def test_media_offsets_come_back_absolute(tmp_path):
    """A DIDX offset is relative to DATA, and both forms are plain integers.
    Handing back the relative one means somebody eventually seeks to it."""
    path = tmp_path / "ok.bnk"
    path.write_bytes(build_bank([("play_x", 5)], media={5: b"abcdef"}))
    _objects, media = wwise.parse_bnk(path)
    offset, size = media[5]
    assert path.read_bytes()[offset : offset + size] == b"abcdef"


def test_a_pack_scales_its_offsets_by_the_block_size(tmp_path):
    path = tmp_path / "p.pck"
    path.write_bytes(build_pack([(9, 16, b"hello"), (10, 1, b"world")]))
    entries = wwise.parse_akpk(path)
    raw = path.read_bytes()
    assert raw[entries[9][1] : entries[9][1] + entries[9][2]] == b"hello"
    assert raw[entries[10][1] : entries[10][1] + entries[10][2]] == b"world"


def test_something_that_is_not_a_pack_is_not_an_error(tmp_path):
    path = tmp_path / "notapack.pck"
    path.write_bytes(b"nope" + b"\x00" * 64)
    assert wwise.parse_akpk(path) == {}


def test_an_event_resolves_through_a_container(tmp_path):
    """Most real events do. The child list has no fixed offset, so it is found
    by shape -- a count followed by that many ids that all name real objects."""
    path = tmp_path / "c.bnk"
    path.write_bytes(build_bank([("play_x", 42)], media={42: b"..."}, container=True))
    objects, _media = wwise.parse_bnk(path)
    assert wwise.resolve_sources(objects, wwise.fnv1_32("play_x")) == [(42, 0)]


def test_an_unknown_name_resolves_to_nothing(tmp_path):
    path = tmp_path / "c.bnk"
    path.write_bytes(build_bank([("play_x", 42)]))
    objects, _media = wwise.parse_bnk(path)
    assert wwise.resolve_sources(objects, wwise.fnv1_32("play_nothing")) == []


# ---- the install surface ----


def _install_with(tmp_path, media_id=7, frames=1, name="play_synth"):
    blob = wem(frame(nibbles=[4]) * frames)
    write_install(tmp_path, banks=[build_bank([(name, media_id)], media={media_id: blob})])
    return wwise.DoomSounds(tmp_path)


def test_a_folder_with_no_soundbanks_is_refused(tmp_path):
    with pytest.raises(wwise.SoundsUnavailableError):
        wwise.DoomSounds(tmp_path)


def test_a_synthesised_install_decodes_end_to_end(tmp_path):
    sounds = _install_with(tmp_path, frames=3)
    channels, rate, per_channel = sounds.pcm("play_synth")
    assert (channels, rate) == (1, 22050)
    assert len(per_channel[0]) == 3 * 64


def test_the_pack_copy_wins_over_the_bank_copy(tmp_path):
    """A media id in both is a prefetch stub in the bank -- the first fraction
    of a second, inline, so playback can start while the stream seeks. It is a
    valid RIFF and it decodes cleanly, into a sound that stops early. Nothing
    about the bytes says they are a fragment, so the rule has to be the source.
    """
    stub = wem(frame(nibbles=[4]))
    full = wem(frame(nibbles=[4]) * 5)
    write_install(
        tmp_path,
        banks=[build_bank([("play_synth", 3)], media={3: stub})],
        packs=[build_pack([(3, 16, full)])],
    )
    sounds = wwise.DoomSounds(tmp_path)
    assert len(sounds.pcm("play_synth")[2][0]) == 5 * 64


def test_mod_banks_outside_the_retail_sound_root_cannot_override_preview(tmp_path):
    """DoomForge injects these into the live game; the stock preview must not.

    Blindly walking the whole install would let a mod event with the same hash
    replace a SnapMap palette sound according to filesystem ordering. Mod
    sounds need an explicit catalog and priority contract before they can join
    the workstation.
    """
    stock = wem(frame(predictor=1200, nibbles=[0]))
    injected = wem(frame(predictor=-1200, nibbles=[0]))
    write_install(
        tmp_path,
        banks=[build_bank([("play_synth", 1)], media={1: stock})],
    )
    mod_folder = tmp_path / "mods" / "doomforge" / "custom-demon" / "sound" / "soundbanks" / "pc"
    mod_folder.mkdir(parents=True)
    (mod_folder / "doom_custom_demon.bnk").write_bytes(
        build_bank([("play_synth", 2)], media={2: injected})
    )

    sounds = wwise.DoomSounds(tmp_path)

    assert sounds.pcm("play_synth")[2][0][0] == 1200


def test_a_name_with_no_event_raises_naming_itself(tmp_path):
    sounds = _install_with(tmp_path)
    with pytest.raises(KeyError) as caught:
        sounds.pcm("play_absent")
    assert "play_absent" in str(caught.value)


def test_a_name_whose_media_is_missing_raises_naming_itself(tmp_path):
    """A DLC sound in a base-game install: the event is there, the audio is
    not. Distinct from an unknown name, and distinct in the message."""
    write_install(tmp_path, banks=[build_bank([("play_synth", 99)])])
    sounds = wwise.DoomSounds(tmp_path)
    with pytest.raises(KeyError) as caught:
        sounds.pcm("play_synth")
    assert "play_synth" in str(caught.value)


def test_names_reports_only_what_it_can_actually_play(tmp_path):
    """Takes candidates rather than enumerating: a bank stores hashes, and
    `fnv1_32` does not run backwards. There is no list of names in there."""
    sounds = _install_with(tmp_path)
    assert sounds.names(["play_synth", "play_absent"]) == {"play_synth"}


def test_the_browser_catalog_keeps_all_play_events_and_marks_local_previewability(tmp_path):
    audio = wem(frame(nibbles=[4]))
    records = build_event_catalog(
        [
            {"name": "Play_Synth", "path": "test/synth/", "bus": "SFX"},
            {"name": "Stop_Synth", "path": "test/synth/", "bus": "SFX"},
            {"name": "Play_Missing", "path": "test/missing/", "bus": "SFX"},
        ]
    )
    write_install(
        tmp_path,
        banks=[
            build_bank(
                [("Play_Synth", 1), ("Stop_Synth", 2), ("Play_Missing", 3)],
                media={1: audio, 2: audio},
            )
        ],
        events=records,
    )

    folder = Path(tmp_path) / wwise.SOUND_SUBDIR
    (folder / wwise.EVENT_XML_NAME).write_text(
        '<Root><Event Name="Play_Synth" DurationType="Mixed"/></Root>',
        encoding="utf-8",
    )
    sounds = wwise.DoomSounds(tmp_path)

    assert [event.name for event in sounds.event_catalog()] == ["Play_Synth", "Play_Missing"]
    assert sounds.event("play_synth").path == "test/synth/"
    assert sounds.event("play_synth").looping is True
    assert sounds.event_is_looping("play_synth") is True
    assert sounds.can_preview("play_synth") is True
    assert sounds.can_preview("play_missing") is False
    assert sounds.event("play_missing") is not None
    assert sounds.event("stop_synth") is None


def test_a_later_available_container_source_is_playable(tmp_path):
    name = "Play_Multi"
    first_sound = 0x41000000
    second_sound = first_sound + 1
    container = first_sound + 2
    action = first_sound + 3
    objects = [
        hirc_object(2, sound_payload(first_sound, 100)),
        hirc_object(2, sound_payload(second_sound, 101)),
        hirc_object(5, container_payload(container, [first_sound, second_sound])),
        hirc_object(3, action_payload(action, container)),
        hirc_object(4, event_payload(wwise.fnv1_32(name), [action])),
    ]
    bank = chunk(b"BKHD", struct.pack("<IIII", wwise.BANK_VERSION, 1, 0, 0))
    audio = wem(frame(nibbles=[4]))
    bank += chunk(b"DIDX", struct.pack("<III", 101, 0, len(audio)))
    bank += chunk(b"DATA", audio)
    bank += chunk(b"HIRC", struct.pack("<I", len(objects)) + b"".join(objects))
    write_install(
        tmp_path,
        banks=[bank],
        events=build_event_catalog([{"name": name, "path": "test/multi/"}]),
    )

    sounds = wwise.DoomSounds(tmp_path)

    assert sounds.names([name]) == {name}
    assert sounds.event(name).name == name
    assert sounds.wav_bytes(name)[:4] == b"RIFF"


def test_the_selected_localised_voice_banks_join_the_retail_banks(tmp_path):
    name = "Play_Voice_Line"
    folder = Path(tmp_path) / wwise.SOUND_SUBDIR
    folder.mkdir(parents=True)
    locale = folder / wwise.DEFAULT_LANGUAGE
    locale.mkdir()
    (locale / "voice.bnk").write_bytes(
        build_bank([(name, 7)], media={7: wem(frame(predictor=700))})
    )
    (folder / wwise.EVENT_CATALOG_NAME).write_bytes(
        build_event_catalog([{"name": name, "path": "doom_vo/test/"}])
    )

    sounds = wwise.DoomSounds(tmp_path)

    assert sounds.language == wwise.DEFAULT_LANGUAGE
    assert sounds.event(name).name == name
    assert sounds.event_is_looping(name) is None
    assert sounds.pcm(name)[2][0][0] == 700


def test_wav_bytes_is_a_readable_wav(tmp_path):
    import io
    import wave

    sounds = _install_with(tmp_path, frames=2)
    with wave.open(io.BytesIO(sounds.wav_bytes("play_synth"))) as reader:
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == 22050
        assert reader.getnframes() == 2 * 64


def test_a_stereo_wav_interleaves_its_channels(tmp_path):
    import io
    import wave

    blob = wem(frame(predictor=1000) + frame(predictor=-1000), channels=2)
    write_install(tmp_path, banks=[build_bank([("play_pair", 1)], media={1: blob})])
    sounds = wwise.DoomSounds(tmp_path)
    with wave.open(io.BytesIO(sounds.wav_bytes("play_pair"))) as reader:
        assert reader.getnchannels() == 2
        assert reader.getnframes() == 64
        first = reader.readframes(1)
    assert struct.unpack("<hh", first) == (1000, -1000)


# ---- the real install ----


@pytest.fixture(scope="module")
def install():
    """The user's own game, or a skip.

    Built once for the module: reading the header of every bank is a few
    seconds and a gigabyte of seeks, and per-test would dominate the suite.
    """
    found = locate.doom_install()
    if found is None:
        pytest.skip("no game install found (see snapmap_midi.audio.locate)")
    return found


@pytest.fixture(scope="module")
def real_sounds(install):
    return wwise.DoomSounds(install)


@pytest.mark.gamedata
def test_every_bank_in_the_install_is_the_measured_version(real_sounds):
    """Construction parses all of them, so reaching here at all is the proof."""
    assert real_sounds.objects
    assert real_sounds.stream


@pytest.mark.gamedata
def test_a_known_pitched_sound_decodes(real_sounds):
    channels, rate, per_channel = real_sounds.pcm("play_pianoc4")
    assert channels == 1
    assert rate > 0
    assert len(per_channel[0]) % 64 == 0
    assert len(per_channel[0]) > 64
    assert any(sample != 0 for sample in per_channel[0])


@pytest.mark.gamedata
def test_the_full_named_catalog_exposes_every_play_event_and_previewable_media(real_sounds):
    events = real_sounds.event_catalog()
    assert len(events) >= 7500
    assert sum(real_sounds.can_preview(event.name) for event in events) >= 7300
    assert real_sounds.event("play_pianoc4") is not None
    assert real_sounds.can_preview("play_pianoc4") is True
    assert all(event.name.lower().startswith("play_") for event in events)


@pytest.mark.gamedata
def test_the_palette_resolves_against_the_install(real_sounds):
    """Every name the shipped palette offers has audio behind it. A name that
    does not is a lane the window can draw and cannot play."""
    from snapmap_midi.sound import palette

    names = [sound for sounds in palette.load_palette().values() for sound in sounds]
    assert real_sounds.names(names) == set(names)
