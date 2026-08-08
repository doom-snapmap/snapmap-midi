"""A mutable map document — the shared authoring surface.

Building a map from nothing is impractical: the editor generates cap entities
and populates reference tables when it SAVES, but does not reconstruct them
when it LOADS. So authoring starts from a known-loadable saved map and applies
minimal mutations, preserving everything the editor generated.

This class carries the operations any map author needs. Anything specific to
reverse-engineering workflows -- wire-chain composition, semantic validation,
round-tripping through a live engine -- belongs in a subclass, not here.

Protected surface: `build_simple_entity`, `extend_instance_entities` and
`add_entity_refs` are public deliberately. Subclasses compose their own entity
kinds out of them, so renaming one silently breaks a downstream author rather
than failing a test here. They are part of the contract.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from snapmap_midi.rawmap import refs as _refs
from snapmap_midi.rawmap import template as _template
from snapmap_midi.rawmap.codec import serialize as _serialize
from snapmap_midi.rawmap.refs import PaletteRefs
from snapmap_midi.rawmap.values import Mat2D, Vec3

SPEAKER_CLASS = "idSnapMapGameEntity_Speaker"
SPEAKER_INHERIT = "snapmaps/audio/2d_speaker"


def speaker_edit(sound: str, position: tuple[float, float, float]) -> dict:
    """A speaker's edit block, matching the shape the editor saves.

    Saved speakers always carry a rotation, so an identity one is emitted for
    shape fidelity even though it encodes no rotation. Position is zero-elided
    like every other vector, so a speaker at the origin has no position key.
    """
    edit: dict[str, Any] = {}
    if sound:
        edit["sound"] = sound
    edit["spawnOrientation"] = Mat2D(angle_radians=0.0)
    pos = Vec3(position[0], position[1], position[2])
    if pos:
        edit["spawnPosition"] = pos
    return edit


class SnapMapDocument:
    """A parsed map plus the mutations that keep it loadable."""

    def __init__(self, data: dict, palette_refs: Optional[PaletteRefs] = None):
        """`palette_refs` maps inherit path to (entity_refs, variable_refs).

        None means no table was supplied, and every reference-authoring call
        will raise. It never means "an empty table, treat everything as zero"
        -- that is the silent default this design exists to remove.
        """
        self.data = data
        self.palette_refs: PaletteRefs = {} if palette_refs is None else palette_refs

    # ---- queries ----

    def entity_count(self) -> int:
        return len(self.data.get("entities", []))

    def max_uid(self) -> int:
        uids = [e.get("uniqueId", 0) for e in self.data.get("entities", [])]
        # Connections count too. Negative entries are sources stored as
        # -(source + 1); non-negative entries are raw target ids.
        conns = self.data.get("targets", {}).get("connections", [])
        uids += [(-c - 1) if c < 0 else c for c in conns]
        return max(uids) if uids else 0

    def next_safe_uid(self) -> int:
        return self.max_uid() + 1

    def find_entity(self, unique_id: int) -> dict:
        for e in self.data["entities"]:
            if e.get("uniqueId") == unique_id:
                return e
        raise KeyError(f"no entity with uniqueId={unique_id}")

    def lookup_class_and_inherit(self, unique_id: int) -> tuple[str | None, str | None]:
        """(className, inherit) for an id, or (None, None) if absent.

        Absent is not an error here: the caller decides whether the id is a
        reserved synthetic one or a genuine mistake.
        """
        for e in self.data.get("entities", []):
            if e.get("uniqueId") == unique_id:
                ed = e.get("entityDef") or {}
                return ed.get("className"), ed.get("inherit")
        return None, None

    # ---- protected surface (see class docstring) ----

    def build_simple_entity(
        self,
        class_name: str,
        unique_id: int,
        inherit: str,
        edit: dict,
        display_name: str = "",
    ) -> dict:
        """The entity wrapper, matching the shape the editor saves."""
        return {
            "customIcon": {
                "targetType": "idDeclSnapCustomIcon",
                "value": None,
                "~type": "|pointer",
            },
            "displayName": display_name,
            "entityDef": {
                "className": class_name,
                "inherit": inherit,
                "name": "",
                "state": {"edit": dict(edit)},
                "targetType": "idDeclEntityDef",
                "~type": "idDeclEntityDef",
                "~version": 26,
            },
            "isMegaModel": False,
            "layerMask": 1,
            "pinned": True,
            "restrictionMask": 0,
            "uniqueId": unique_id,
            "~type": "idSnapEntity",
        }

    def extend_instance_entities(self, unique_id: int, owning_instance: int) -> None:
        """Record the new id against its owning instance.

        `keyValues` is a prefix sum over instances, so adding to instance i
        means inserting at the end of i's slice and bumping every later key.
        """
        ie = self.data["instanceEntities"]
        keys = ie["keyValues"]
        values = ie["values"]
        insert_at = keys[owning_instance + 1]
        values.insert(insert_at, unique_id)
        for j in range(owning_instance + 1, len(keys)):
            keys[j] += 1

    def add_entity_refs(
        self,
        unique_id: int,
        inherit: str,
        palette_refs: Optional[PaletteRefs] = None,
    ) -> None:
        """Author the reference slots this inherit path requires.

        `palette_refs` overrides the document's table for this one call, so a
        caller can supply a fallback without mutating shared state.
        """
        table = self.palette_refs if palette_refs is None else palette_refs
        _refs.add_entity_refs(self.data, unique_id, inherit, table)

    # ---- mutations ----

    def add_speaker(
        self,
        unique_id: Optional[int] = None,
        sound: str = "play_pianoc4",
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        display_name: str = "",
        owning_instance: int = 0,
    ) -> int:
        """Add a speaker entity, maintaining every table that must agree.

        A speaker is never a raw wire endpoint: its output is caught by a
        listener node. Returns the assigned id.
        """
        if unique_id is None:
            unique_id = self.next_safe_uid()

        entity = self.build_simple_entity(
            SPEAKER_CLASS,
            unique_id,
            SPEAKER_INHERIT,
            speaker_edit(sound, position),
            display_name=display_name,
        )
        self.data["entities"].append(entity)
        self.extend_instance_entities(unique_id, owning_instance)
        # The speaker pair is (0, 0), so this only sizes the key tables --
        # but routing through the same writer keeps every authoring path
        # consistent, and catches a missing table entry here rather than in
        # game.
        self.add_entity_refs(unique_id, SPEAKER_INHERIT)
        return unique_id

    def module_stem(self, instance: int = 0) -> str:
        """The bare module name an entity reference string is built from."""
        name = self.data["instances"][instance]["moduleName"]
        return name.rsplit("/", 1)[-1].rsplit(".", 1)[0]

    def find_timeline(self) -> Optional[dict]:
        """The first timeline entity, or None if the document has none."""
        for e in self.data.get("entities", []):
            if (e.get("entityDef") or {}).get("className") == _template.TIMELINE_CLASS:
                return e
        return None

    def add_timeline(self, unique_id: Optional[int] = None, owning_instance: int = 0) -> dict:
        """Add a timeline entity with one empty event group. Returns it.

        A timeline is an ordinary entity in a saved map — class
        `idTarget_Timeline`, stock inherit, reference pair (0, 0). It is not
        placeable from the editor's palette, which is a fact about the EDITOR
        and was long mistaken for a fact about the format; describing one here
        is no harder than describing a speaker.
        """
        if unique_id is None:
            unique_id = self.next_safe_uid()

        entity = _template.timeline_entity(unique_id, self.module_stem(owning_instance))
        self.data["entities"].append(entity)
        self.extend_instance_entities(unique_id, owning_instance)
        self.add_entity_refs(unique_id, _template.TIMELINE_INHERIT)
        return entity

    def ensure_timeline(self, owning_instance: int = 0) -> dict:
        """The document's timeline, authoring one if it has none.

        This is what makes a baseline map optional. A document that already
        carries a timeline — a map saved out of the editor, say — keeps the
        one it has, so existing arrangements are untouched.
        """
        return self.find_timeline() or self.add_timeline(owning_instance=owning_instance)

    def add_connection(self, source_uid: int, target_uid: int) -> None:
        """Wire `source_uid` to fire into `target_uid`.

        Connections use a signed run-length encoding:
            -(S+1), T1, T2, ..., -(S2+1), T1', ...
        A negative entry opens a run for source S; the non-negative entries
        after it are the targets S fires into, stored as raw ids.

        The +1 bias is required: the engine decodes a source as |stored| - 1,
        so id 0 is representable as -1 and stays distinct from target 0.
        Decoded from two saved samples: speaker(62) to listener(63) stores
        [-63, 63] -- which is NOT a self-loop, because 62+1 collides with the
        listener's real id -- and the chain 62,63,64,61 stores
        [-63,63,-64,64,-65,61].

        This is a low-level primitive and does not check the edge is
        meaningful. Valid wiring routes output through a node to an input; a
        raw entity-to-entity edge is a topology error.
        """
        if source_uid <= 0 or target_uid < 0:
            raise ValueError(
                f"connections must have positive source ({source_uid}) and "
                f"non-negative target ({target_uid}); negative entries are "
                f"the run markers"
            )
        conns = self.data.setdefault("targets", {}).setdefault("connections", [])
        marker = -(source_uid + 1)
        try:
            idx = conns.index(marker)
        except ValueError:
            conns.extend([marker, target_uid])
            return
        end = idx + 1
        while end < len(conns) and conns[end] >= 0:
            end += 1
        conns.insert(end, target_uid)

    def get_connections_for_source(self, source_uid: int) -> list[int]:
        """The targets `source_uid` currently fires into."""
        conns = self.data.get("targets", {}).get("connections", [])
        marker = -(source_uid + 1)
        try:
            idx = conns.index(marker)
        except ValueError:
            return []
        end = idx + 1
        targets: list[int] = []
        while end < len(conns) and conns[end] >= 0:
            targets.append(conns[end])
            end += 1
        return targets

    # ---- output ----

    def serialize(self) -> bytes:
        return _serialize(self.data)

    def to_dict(self) -> dict:
        """A deep copy, for inspection."""
        return copy.deepcopy(self.data)

    def clone(self) -> "SnapMapDocument":
        """Deep copy, preserving the concrete class.

        Constructs `type(self)` rather than naming a class: naming this one
        would make a subclass silently degrade to the base on clone, and
        naming a subclass would invert the dependency.
        """
        return type(self)(data=copy.deepcopy(self.data), palette_refs=self.palette_refs)
