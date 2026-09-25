"""Test-suite wiring: keep the app away from every production service.

`api.main` calls load_dotenv(), which never overrides a variable that is already set, so the values
below — set before anything imports the app — win over `.env`:

- REDIS_URL: an unsupported scheme makes redis.from_url() fail at once, so the app uses its in-memory
  mock. Without this the suite wrote live-timing keys into the real (production) Upstash Redis. (A
  closed port works too, but Windows takes ~2s to refuse each connection.)
- DATABASE_URL empty: local DuckDB instead of Supabase, so app start-up doesn't connect to production
  and the background model warm-up doesn't train on — or write its cache to — the production database.
- DUCKDB_PATH / MODEL_DIR / CACHE_DIR: a throwaway directory, so the committed DuckDB file, saved
  models and `cache/` files are never touched (the response cache deletes expired files at start-up).
"""
import os
import tempfile

_scratch = tempfile.mkdtemp(prefix="shif1-tests-")

os.environ["REDIS_URL"] = "unset://tests-use-the-in-memory-mock"
os.environ["DATABASE_URL"] = ""
os.environ["DUCKDB_PATH"] = os.path.join(_scratch, "f1_test.duckdb")
os.environ["MODEL_DIR"] = os.path.join(_scratch, "models")
os.environ["CACHE_DIR"] = os.path.join(_scratch, "cache")
# No live OpenF1 feed in tests (it would also start the live schedule at app start-up).
os.environ["OPENF1_USERNAME"] = ""
os.environ["OPENF1_PASSWORD"] = ""

import pytest


@pytest.fixture(autouse=True)
def _no_background_model_warmup(monkeypatch):
    """App start-up trains the prediction models in a worker thread. The tests start and stop the app
    many times, and stopping it closes the DuckDB connection under a training thread that is still
    reading it — which crashes the interpreter on Windows. No test needs the warm-up."""
    import api.main as main

    async def _skip():
        return None

    monkeypatch.setattr(main, "_warm_prediction_models", _skip)
