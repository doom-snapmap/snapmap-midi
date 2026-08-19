"""Embedded value builders — the JSON shapes the map format uses for structs.

These match the shapes observed in saved maps. They omit zero components,
because the format itself does: a vector at the origin serializes as an empty
object, not as three explicit zeros. Emitting the zeros instead would be
semantically identical and byte-different.
"""

from __future__ import annotations

import math


def Vec3(x: float = 0.0, y: float = 0.0, z: float = 0.0, tagged: bool = False) -> dict:
    """A 3-vector, normally inlined as {x, y, z}.

    Set tagged=True to include the ~type marker, which is required when the
    vector is the top-level value of a struct field rather than nested.
    """
    out: dict = {}
    if x != 0.0:
        out["x"] = x
    if y != 0.0:
        out["y"] = y
    if z != 0.0:
        out["z"] = z
    if tagged:
        out["~type"] = "idVec3"
    return out


def Mat3(rows: list[tuple[float, float, float]] | None = None) -> dict:
    """A 3x3 matrix, encoded as {mat: {mat[0]: {x,y,z}, ...}}.

    Defaults to identity. Zero components are omitted per row, matching Vec3.
    """
    if rows is None:
        rows = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    mat: dict = {}
    for i, row in enumerate(rows):
        row_dict: dict = {}
        for axis, v in zip(("x", "y", "z"), row):
            if v != 0.0:
                row_dict[axis] = v
        if row_dict:
            mat[f"mat[{i}]"] = row_dict
    return {"mat": mat}


def Mat2D(angle_radians: float = 0.0) -> dict:
    """A rotation about the vertical axis only — the common entity case.

    Two rows, which is what saved maps carry, and both components of each row
    are written even when one is zero. `Mat3` omits zero components the way
    `Vec3` does, and that is right for a position -- an engine-saved cap is
    `{"y": 3840}` with no x or z -- but wrong here: the same file writes that
    cap's rotation row as `{"x": 0, "y": 1}`. The format has two rules and
    this is the other one.
    """
    c, s = math.cos(angle_radians), math.sin(angle_radians)
    return {
        "mat": {
            "mat[0]": {"x": c, "y": s},
            "mat[1]": {"x": -s, "y": c},
        }
    }


def Pointer(target_type: str, value: str | None = None) -> dict:
    """A declaration pointer: {targetType, value, ~type: "|pointer"}."""
    return {"targetType": target_type, "value": value, "~type": "|pointer"}
