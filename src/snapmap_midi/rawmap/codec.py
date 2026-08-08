"""Map serialization: the compact JSON dialect the editor reads and writes.

The format is JSON with three properties that a stock encoder does not give you:

  - keys are emitted in insertion order, NOT sorted;
  - floats use C-style exponents (no leading zero, no '+' on positive); and
  - floats round-trip at 64-bit shortest-representation precision.

Roughly 0.5% of float literals differ from the engine's own writer by one unit
in the last place, because two shortest-round-trip algorithms can pick different
digit strings for the same double. Both parse back to the identical value, so
semantic round-trip (parse, emit, parse, compare) is exact.

Key order is load-bearing. Anything that derives a mapping from a structured
record emits it in field declaration order, so reordering fields changes bytes
with no semantic change at all.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ──────────────────────────────────────────────────────────────────
# Float formatting
# ──────────────────────────────────────────────────────────────────

_EXP_RE = re.compile(r"(\d)e([+-])?0*(\d+)")


def _normalize_exp(s: str) -> str:
    """Rewrite 'e+07'/'e-07' into the 'e7'/'e-7' style the format uses."""
    return _EXP_RE.sub(
        lambda m: f"{m.group(1)}e{m.group(2) if m.group(2) == '-' else ''}{m.group(3)}", s
    )


def _format_float(f: float) -> str:
    """Float to its decimal string in this dialect.

    Only values whose repr already carries an exponent are normalized; 1e7
    reprs as '10000000.0' and is emitted verbatim.
    """
    if f != f:  # NaN
        return "NaN"
    if f == float("inf"):
        return "Infinity"
    if f == float("-inf"):
        return "-Infinity"
    # repr gives the shortest round-trip form at 64-bit precision.
    return _normalize_exp(repr(f))


# ──────────────────────────────────────────────────────────────────
# Serializer
# ──────────────────────────────────────────────────────────────────


def _emit(obj: Any, out: list) -> None:
    """Streaming emit into `out` (a list of string fragments)."""
    if obj is None:
        out.append("null")
    elif obj is True:
        out.append("true")
    elif obj is False:
        out.append("false")
    elif isinstance(obj, int) and not isinstance(obj, bool):
        out.append(str(obj))
    elif isinstance(obj, float):
        out.append(_format_float(obj))
    elif isinstance(obj, str):
        # json.dumps handles every string escape rule correctly.
        out.append(json.dumps(obj, ensure_ascii=False))
    elif isinstance(obj, list):
        out.append("[")
        for i, v in enumerate(obj):
            if i:
                out.append(",")
            _emit(v, out)
        out.append("]")
    elif isinstance(obj, dict):
        out.append("{")
        for i, (k, v) in enumerate(obj.items()):
            if i:
                out.append(",")
            out.append(json.dumps(k, ensure_ascii=False))
            out.append(":")
            _emit(v, out)
        out.append("}")
    else:
        raise TypeError(f"Cannot serialize type {type(obj).__name__}: {obj!r}")


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────


def deserialize(raw: bytes) -> Any:
    """Parse map bytes into the in-memory representation.

    Dicts preserve insertion order, so key order survives deserialize into
    serialize as long as nothing sorts.
    """
    return json.loads(raw.decode("utf-8"))


def serialize(obj: Any) -> bytes:
    """Serialize the in-memory representation back to map bytes."""
    out: list[str] = []
    _emit(obj, out)
    return "".join(out).encode("utf-8")
