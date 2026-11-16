"""Put the package root and this directory on sys.path (no install step)."""

import sys
from pathlib import Path

for _p in (Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
