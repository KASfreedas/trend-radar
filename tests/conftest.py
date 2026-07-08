"""Shared test setup — puts the repo root on sys.path so `briefing` and
`scrapers` import the same way they do when app.py runs from the root."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
