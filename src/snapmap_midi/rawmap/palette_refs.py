"""Reference-slot counts for every palette entry this product authors.

snapmap-midi creates a handful of entity kinds, so its table is small enough to
state explicitly and defend entry by entry, rather than extracted in bulk from
saved maps.

Provenance differs per entry, and the difference matters:

  - The speaker and listener pairs are observed directly in engine-saved maps.
  - The timeline, cap and player-start pairs are likewise observed directly,
    read out of an engine-saved map of the same blank-room module this product
    now authors from scratch.
  - The switch pair is NOT. No saved sample in hand contains one. Its entity
    count of 1 is shared by all twelve observed entries under the same palette
    prefix, so it is well supported. Its variable count of 0 is inference: of
    the nine entries annotated as the plain interactable class, six are exactly
    (1, 0), and three carry non-zero variable counts of 9, 10 and 4. It is
    proven only to the extent that maps built with it load and play.

Treat a disagreeing engine-saved sample as authoritative over this file. A
change to the switch pair moves serialized bytes and needs re-proving in game,
not a fixture refresh.
"""

from __future__ import annotations

from snapmap_midi.rawmap.template import TEMPLATE_PALETTE_REFS

SPEAKER_INHERIT = "snapmaps/audio/2d_speaker"
LISTENER_ON_USE_INHERIT = "snapmaps/listener/interactable/on_use"
SWITCH_INHERIT = "snapmaps/interactibles/crate_switch"

PRODUCT_PALETTE_REFS: dict[str, tuple[int, int]] = {
    SPEAKER_INHERIT: (0, 0),
    LISTENER_ON_USE_INHERIT: (0, 1),
    SWITCH_INHERIT: (1, 0),
    # The stage this product authors around the song: the timeline itself, the
    # two portal caps and the player start.
    **TEMPLATE_PALETTE_REFS,
}
