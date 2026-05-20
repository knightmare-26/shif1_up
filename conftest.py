"""Project-level pytest config.

`api/main.py` imports its service modules as `from services.xxx import ...`,
which relies on `api/` being on PYTHONPATH at runtime (see start_backend.py).
This conftest mirrors that so `pytest` from the project root can import the app.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
API_DIR = ROOT / "api"

for p in (str(ROOT), str(API_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DUCKDB_PATH", str(ROOT / "data" / "f1_history.duckdb"))
os.environ.setdefault("FASTF1_CACHE_DIR", str(ROOT / "data" / "fastf1_cache"))
