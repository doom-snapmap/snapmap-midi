"""Map authoring core — read, mutate and write the editor's map format.

This layer knows nothing about music. It is kept independently promotable: a
future non-music tool can depend on it as an ordinary library, and a test in
the product suite asserts it never imports the music modules above it.
"""

from __future__ import annotations

from snapmap_midi.rawmap.codec import deserialize, serialize
from snapmap_midi.rawmap.values import Mat2D, Mat3, Pointer, Vec3

__all__ = ["deserialize", "serialize", "Vec3", "Mat3", "Mat2D", "Pointer"]
