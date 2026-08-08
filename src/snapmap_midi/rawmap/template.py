"""A blank, loadable map document authored from nothing.

Authoring used to start from a saved map the user supplied, for two stated
reasons. Both are addressed here.

The first was structural: the editor generates cap entities and populates the
reference tables when it SAVES and does not reconstruct them when it LOADS, so
a document missing them is rejected. That is still true — which is why this
module authors them explicitly rather than omitting them.

The second was the timeline. `idTarget_Timeline` is not placeable from the
stock entity palette, so the conclusion drawn at the time was that a timeline
had to be inherited from an existing map. That conflated two different things:
making the engine SPAWN a timeline at runtime, which really is not possible
from outside, and DESCRIBING one in a saved map, which is just schema. A
timeline in a saved map is an ordinary entity whose class is
`idTarget_Timeline` and whose inherit is the stock `snapmaps/unknown`, and its
reference-slot pair is (0, 0) — the cheapest entry in the whole table.

Every constant below is schema: engine class names, stock declaration paths,
and structural shapes. No game content is reproduced here.

The geometry is one blank room module with its two portals capped. That is the
smallest thing that is still a real, walkable map, and it is deliberately
boring: this is a stage for a song, not a level.
"""

from __future__ import annotations

from typing import Any

#: The empty room the song is staged in, and where the engine puts it.
DEFAULT_MODULE = "maps/modules/ind_dlc/ind_totally_blank_room_4x.decl"
DEFAULT_ENVIRONMENT = "snapmap/base"
DEFAULT_ORIGIN = (1152.0, -2944.0, 0.0)

#: Format revision. The engine writes this in two places and checks both.
MAP_VERSION = 111

#: The stock inherit a timeline carries in a saved map. It is NOT the decl a
#: timeline is spawned from in the editor — that is a repurposed placeholder,
#: and a map naming it would only reload where that override is installed.
#: This is the portable one, and it is what engine-saved maps settle on.
TIMELINE_INHERIT = "snapmaps/unknown"
TIMELINE_CLASS = "idTarget_Timeline"

#: The player spawn. `add_button` anchors the switch to it, so a map without
#: one would put the switch at the origin and out of reach.
PLAYER_START_INHERIT = "player/coop/player_start"
PLAYER_START_CLASS = "idSnapMapGameEntity_ComboStart"

#: The two portal caps that seal the room. A module's portals must be either
#: joined to a neighbour or capped; uncapped ones leave the map open to
#: nothing and it is rejected.
CAP_CLASS = "idSnapMapCapEntity"
CAP_DOOR_DECL = "doors/industrial_door_vertical"
CAP_CLOSED_STATE = "interactables/doors/snap_door/Normal/Closed"

#: Reserved ids. They are fixed rather than allocated because `doorsAndCaps`
#: refers to the caps by id, and because keeping them where an engine-saved
#: map puts them keeps this document comparable to one.
CAP_A_UID = 56
CAP_B_UID = 57
PLAYER_START_UID = 61
TIMELINE_UID = 62

#: How far the reference tables are padded. They are prefix-sum indexed by
#: unique id and the engine walks the whole array, so they must cover the id
#: space rather than only the ids in use. This is the width an engine-saved
#: map of this module carries.
REFERENCE_TABLE_WIDTH = 471

#: Reference-slot pairs for the entities this template authors, observed
#: directly in an engine-saved map of the same module.
TEMPLATE_PALETTE_REFS: dict[str, tuple[int, int]] = {
    "snapmaps/visblockers/industrial/cap_05": (1, 0),
    "snapmaps/visblockers/industrial/cap_10": (1, 0),
    PLAYER_START_INHERIT: (1, 0),
    TIMELINE_INHERIT: (0, 0),
}

#: The ten variable kinds a map carries, in the order the format lists them.
#: `allocCount` is parallel to this list, which is why the two stay together.
_VARIABLE_KINDS = (
    "boolean",
    "cachedEntity",
    "color",
    "customEvent",
    "integer",
    "number",
    "persistentInteger",
    "playerResource",
    "string",
    "teamResource",
)


def _rotation(mat0: dict, mat1: dict) -> dict:
    """A rotation in the two-row form saved maps use for placed entities."""
    return {"mat": {"mat[0]": mat0, "mat[1]": mat1}}


def _cap_entity(unique_id: int, cap_number: str, y: float, mat0: dict, mat1: dict) -> dict:
    """One portal cap, facing along the room's long axis."""
    return {
        "customIcon": {"targetType": "idDeclSnapCustomIcon", "value": None, "~type": "|pointer"},
        "displayName": "",
        "entityDef": {
            "className": CAP_CLASS,
            "inherit": "snapmaps/visblockers/industrial/cap_" + cap_number,
            "name": "",
            "state": {
                "edit": {
                    "interaction": {"initalState": CAP_CLOSED_STATE},
                    "props": {
                        "capDecl": "doors/industrial_cap_" + cap_number,
                        "doorDecl": CAP_DOOR_DECL,
                    },
                    "spawnOrientation": _rotation(mat0, mat1),
                    "spawnPosition": {"y": y},
                }
            },
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


def _player_start(unique_id: int) -> dict:
    """Where the player spawns, near the middle of the room."""
    return {
        "customIcon": {"targetType": "idDeclSnapCustomIcon", "value": None, "~type": "|pointer"},
        "displayName": "",
        "entityDef": {
            "className": PLAYER_START_CLASS,
            "inherit": PLAYER_START_INHERIT,
            "name": "",
            "state": {"edit": {"spawnPosition": {"x": -1397.0, "y": 1409.0, "z": 0.5}}},
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


def timeline_entity_id(module_stem: str, unique_id: int, instance: int = 0) -> str:
    """The self-reference string a timeline uses to name its own event group.

    The format is `<instance>_<module stem>/<inherit>_<id>`, the same shape
    every other entity reference in the document uses.
    """
    return "%d_%s/%s_%d" % (instance, module_stem, TIMELINE_INHERIT, unique_id)


def timeline_entity(unique_id: int, module_stem: str, instance: int = 0) -> dict:
    """A timeline entity with one empty event group, ready to be filled.

    The group is created here rather than by the caller because a timeline
    with no groups at all has nowhere to put its first event, and callers
    would each have to know the shape to add one.
    """
    return {
        "customIcon": {"targetType": "idDeclSnapCustomIcon", "value": None, "~type": "|pointer"},
        "displayName": "",
        "entityDef": {
            "className": TIMELINE_CLASS,
            "inherit": TIMELINE_INHERIT,
            "name": "",
            "state": {
                "edit": {
                    "componentTimeLine": {
                        "entityEvents": {
                            "item[0]": {
                                "entity": timeline_entity_id(module_stem, unique_id, instance),
                                "events": {"num": 0},
                            },
                            "num": 1,
                        }
                    },
                    "spawnPosition": {"x": -1276.0, "y": 1226.0, "z": 0.5},
                }
            },
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


def _references(uids_with_one_ref) -> dict:
    """Both reference tables, prefix-sum indexed by unique id.

    `keyValues[i]` is where entity `i`'s bucket starts, so the array is the
    running total of every slot authored before it. Padding to the full width
    matters: the engine walks the whole array, not only the part in use.
    """
    ordered = sorted(uids_with_one_ref)
    ent_keys, running = [], 0
    for uid in range(REFERENCE_TABLE_WIDTH):
        ent_keys.append(running)
        if uid in ordered:
            running += 1
    return {
        "entityEntRefs": {
            "keyValues": ent_keys,
            "values": [-1] * len(ordered),
            "~type": "idIndexMultimap",
        },
        "entityVarRefs": {
            "keyValues": [0] * REFERENCE_TABLE_WIDTH,
            "values": [],
            "~type": "idIndexMultimap",
        },
        "~type": "idSnapReferences",
    }


def blank_map(module: str = DEFAULT_MODULE, with_timeline: bool = True) -> dict:
    """A complete, loadable map document containing nothing but a stage.

    Key order is load-bearing throughout — the format preserves insertion
    order rather than sorting — so the top-level keys are emitted in the order
    an engine-saved map carries them.

    Pass `with_timeline=False` for a stage with no scheduler, which is what a
    caller wants when it intends to author its own.
    """
    module_stem = module.rsplit("/", 1)[-1].rsplit(".", 1)[0]

    entities = [
        _cap_entity(CAP_A_UID, "05", 3840.0, {"y": 1}, {"x": -1}),
        _cap_entity(CAP_B_UID, "10", -1280.0, {"y": -1}, {"x": 1}),
        _player_start(PLAYER_START_UID),
    ]
    ref_uids = [CAP_A_UID, CAP_B_UID, PLAYER_START_UID]
    if with_timeline:
        entities.append(timeline_entity(TIMELINE_UID, module_stem))

    data: dict[str, Any] = {
        "customFilterAllocCount": 0,
        "doorsAndCaps": {
            "portalDoors": [CAP_A_UID, CAP_B_UID],
            "portalFrames": [-1, -1],
            "~type": "idSnapDoorsAndCaps",
        },
        "entities": entities,
        "instanceEntities": {
            "keyValues": [0, len(entities), len(entities)],
            "values": [e["uniqueId"] for e in entities],
            "~type": "idIndexMultimap",
        },
        "instances": [
            {
                "difficultyOffset": 0,
                "environmentName": DEFAULT_ENVIRONMENT,
                "layerMask": 1,
                "moduleName": module,
                "orientation": 0,
                "origin": {
                    "x": DEFAULT_ORIGIN[0],
                    "y": DEFAULT_ORIGIN[1],
                    "z": DEFAULT_ORIGIN[2],
                    "~type": "idVec3",
                },
                "restrictionMask": 0,
                "~type": "idSnapInstance",
            }
        ],
        "references": _references(ref_uids),
        "snapSlotSettings": [
            {"race": 0, "state": 0, "team": team, "~type": "snapLobbySlotSetting_t"}
            for team in (0, 0, 1, 1)
        ],
        "tags": [],
        "targets": {
            "connections": [],
            "entitySources": {"keyValues": [], "values": [], "~type": "idIndexMultimap"},
            "entityTargets": {"keyValues": [], "values": [], "~type": "idIndexMultimap"},
            "~type": "idSnapTargets",
        },
        "useIntroFadeIn": False,
        "useSPLimits": False,
        "useSPModels": False,
        "variables": _variables(),
        "version": MAP_VERSION,
        "~type": "idSnapMap",
        "~version": MAP_VERSION,
    }
    return data


def _variables() -> dict:
    """An empty variable table.

    `allocCount` runs parallel to the kind list and counts how many names have
    ever been handed out per kind, so all-zeros is the only value consistent
    with every list being empty. A saved map from the editor carries the
    editor's own defaults here; a map authored from nothing has none.
    """
    table: dict[str, Any] = {"allocCount": [0] * len(_VARIABLE_KINDS)}
    for kind in _VARIABLE_KINDS:
        table[kind] = []
    table["~type"] = "idSnapVariables"
    return table
