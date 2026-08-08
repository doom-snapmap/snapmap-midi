"""Entry point: python -m snapmap_midi"""

from __future__ import annotations

import sys

from snapmap_midi.cli import main

if __name__ == "__main__":
    sys.exit(main())
