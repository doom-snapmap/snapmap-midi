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

    Emits two rows rather than three, which is what saved maps carry.
    """
    c, s = math.cos(angle_radians), math.sin(angle_radians)
    return Mat3([(c, s, 0.0), (-s, c, 0.0)])


def Pointer(target_type: str, value: str | None = None) -> dict:
    """A declaration pointer: {targetType, value, ~type: "|pointer"}."""
    return {"targetType": target_type, "value": value, "~type": "|pointer"}
