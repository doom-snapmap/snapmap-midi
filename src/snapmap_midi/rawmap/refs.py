"""Reference-slot authoring for newly created entities.

The engine validator at RVA 0x5F27C0 checks every entity's entity-reference and
variable-reference bucket sizes against the pair recorded for its inherit path.
An entity missing those slots fails the integrity check and the map is rejected
at load. The slots are written as unbound sentinels: the entity declares how
many references it will have, and what they point at is bound later.

Both tables are prefix-sum indexed by unique id. `keyValues[uid]` is where that
id's bucket starts, so authoring `count` slots means inserting `count`
sentinels at that offset and bumping every later key by the same amount. The
tables must be readable one entry past the id being authored, hence the pad.

The count table itself is NOT baked in here. It is supplied by the caller,
because different consumers legitimately have different tables: a tool that
authors three kinds of entity can name its three pairs explicitly and defend
them, while one that authors arbitrary entities needs a table extracted from
saved maps. Single-sourcing the mechanism while partitioning the data is the
point -- the alternative was the same twenty lines hand-copied per consumer,
with the counts baked in, which is exactly how they drifted.
"""

from __future__ import annotations

from typing import Mapping

#: A mapping from inherit path to (entity_refs, variable_refs).
PaletteRefs = Mapping[str, "tuple[int, int]"]

#: Sentinels meaning "this slot exists but is not bound to anything yet".
ENT_REF_UNBOUND = -1
VAR_REF_UNBOUND = 16777215


class UnknownInheritError(KeyError):
    """Raised when no reference-count pair is known for an inherit path.

    Defaulting a miss to (0, 0) authors an entity with no reference slots,
    which the engine rejects at load as a corrupted map -- and it does so
    silently, at the point of use, far from the code that guessed. Failing at
    author time instead is the whole reason this is an error.
    """


def add_entity_refs(
    data: dict,
    unique_id: int,
    inherit: str,
    palette_refs: PaletteRefs,
) -> None:
    """Author the reference slots a new entity's inherit path requires."""
    if inherit not in palette_refs:
        raise UnknownInheritError(
            "no reference-count pair known for %r; authoring it would produce a "
            "map the engine rejects at load" % (inherit,)
        )
    n_ent, n_var = palette_refs[inherit]
    for table_key, count, sentinel in (
        ("entityEntRefs", n_ent, ENT_REF_UNBOUND),
        ("entityVarRefs", n_var, VAR_REF_UNBOUND),
    ):
        table = data["references"][table_key]
        keys = table["keyValues"]
        vals = table["values"]
        needed = unique_id + 2  # readable one past this id
        if len(keys) < needed:
            keys.extend([keys[-1] if keys else 0] * (needed - len(keys)))
        if count:
            start = keys[unique_id]  # this id's (currently empty) bucket
            vals[start:start] = [sentinel] * count
            for j in range(unique_id + 1, len(keys)):
                keys[j] += count
