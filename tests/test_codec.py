"""Codec behaviour that the byte gates downstream depend on."""

from __future__ import annotations

import pytest

from snapmap_midi.rawmap import codec, values


def test_roundtrip_preserves_key_order():
    """Key order is load-bearing: the whole byte-gate discipline rests on the
    codec never sorting."""
    raw = b'{"b":1,"a":2}'
    assert codec.serialize(codec.deserialize(raw)) == raw


def test_c_style_float_exponents():
    """Only values whose repr already carries an exponent are normalized.
    1e7 reprs as 10000000.0 and is emitted verbatim -- asserting otherwise
    would send a reader off to 'fix' a correct codec."""
    assert codec.serialize(1e16) == b"1e16"
    assert codec.serialize(1e17) == b"1e17"
    assert codec.serialize(1e-7) == b"1e-7"
    assert codec.serialize(1e7) == b"10000000.0"


def test_non_finite_floats():
    assert codec.serialize(float("nan")) == b"NaN"
    assert codec.serialize(float("inf")) == b"Infinity"
    assert codec.serialize(float("-inf")) == b"-Infinity"


def test_bool_is_not_treated_as_int():
    assert codec.serialize({"a": True, "b": 1}) == b'{"a":true,"b":1}'


def test_rejects_unserializable_type():
    with pytest.raises(TypeError):
        codec.serialize({1, 2})


def test_vec3_omits_zero_components():
    """The format omits zeros; emitting them would be byte-different for no
    semantic change."""
    assert values.Vec3() == {}
    assert values.Vec3(1.0, 0.0, 2.0) == {"x": 1.0, "z": 2.0}
    assert values.Vec3(tagged=True) == {"~type": "idVec3"}


def test_mat2d_emits_two_rows():
    m = values.Mat2D(0.0)["mat"]
    assert set(m) == {"mat[0]", "mat[1]"}
    assert m["mat[0]"] == {"x": 1.0}
    assert m["mat[1]"] == {"y": 1.0}


def test_pointer_shape():
    assert values.Pointer("sound", "play_pianoc4") == {
        "targetType": "sound",
        "value": "play_pianoc4",
        "~type": "|pointer",
    }
