"""
F1 Race & Qualifying Prediction Service
- Qualifying/Race/Sprint: LightGBM rankers (LGBMRanker, lambdarank) predict finishing
  order per race — a ranking objective, not absolute-position regression, since what
  matters is who finishes ahead of whom, not each driver's position as an independent
  number. Predictions are shown as plain rank (#1, #2, ...), not a fractional estimate.
- Training:   Exponential time decay (1.5^(year - oldest)) — recent seasons weighted higher
- Persistence: Models saved to data/models/ and reloaded on startup (no cold retrain)
"""

import json
import logging
import asyncio
import hashlib
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from services.backtest_scores import add_probabilities, hit_rates
from services.practice_features import COLUMNS as PRACTICE_COLUMNS, practice_features
from services import preseason_testing
from services.season_form import QUALI_INPUTS as SEASON_QUALI, RACE_INPUTS as SEASON_RACE, add_season_form, team_points_after

logger = logging.getLogger(__name__)

# Exponential decay factor — 2024 gets 1.5^4 ≈ 5× the weight of 2020
TIME_DECAY = 1.5

# Same-weekend practice inputs (services/practice_features.py), used once most training rows have
# practice. Phase 1 (#30) measured which of them earn their place — see CLAUDE.md. Where a weekend
# has no practice (an upcoming race, the title simulation) they're filled with the training
# medians: filling them with 10 like other inputs made predictions worse than not using practice.
# Preseason testing (services/preseason_testing.py, Phase 3b #35): in an era-start season
# (preseason_testing.ERA_STARTS) the first races' form inputs start from the testing order and blend
# into the real ones over TESTING_RACES races. Walk-forward on the two era starts (2022, 2026; races
# 1-3): qualifying 2.92 -> 2.53 places off (2026 alone 2.98 -> 2.26), race 4.10 -> 4.05, later races
# within noise. Testing as model inputs ("features", every season or era starts only) was worse: the
# model learns mostly from stable seasons, where testing order is a worse guide than last season's.
# Not used for the title simulation: for the season-long order, last season's form did slightly better.
TESTING_MODE = "rule"     # "off" | "features" | "features_era" | "rule"
TESTING_RACES = 3

# The qualifying model learns the qualifying result (Phase 2, #31), falling back to the starting grid
# where no qualifying is stored. The grid isn't the qualifying order: grid penalties, and on 2022
# sprint weekends the sprint set it. Walk-forward: 0.19 places better (t = -2.7), even judged on the grid.
QUALI_TARGET = "quali_target"

PRACTICE_INPUTS = ["driver_practice_best_rank", "driver_practice_gap_pct",
                   "team_practice_gap_pct", "driver_practice_teammate_gap_pct"]

# Features used when grid data is available (after re-ingest)
RACE_FEATURES_FULL = [
    "grid", "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
] + SEASON_RACE   # season-to-date form (services/season_form.py)

# Fallback when grid is NULL (before re-ingest)
RACE_FEATURES_NO_GRID = [
    "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
] + SEASON_RACE

QUALI_FEATURES = [
    "driver_rolling_grid", "driver_circuit_grid_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
] + SEASON_QUALI

# Sprint race features mirror the race model's, but use the sprint grid
# (from sprint qualifying) instead of the main race grid as the input —
# everything else (form, circuit avg, dnf rate) is shared driver/constructor
# state going into that race weekend, not sprint-specific.
SPRINT_FEATURES_FULL = [
    "sprint_grid", "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]

SPRINT_FEATURES_NO_GRID = [
    "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]


class PredictionService:
    # Everything a training run produces. Fitting happens on a private copy holding these
    # and the result is swapped in all at once, so requests never see half-updated models.
    _FITTED = (
        "_race_model", "_quali_model", "_sprint_model",
        "_race_features", "_quali_features", "_sprint_features",
        "_df", "_driver_map", "_constructor_map", "_le_driver", "_le_constructor", "_le_circuit",
        "_trained", "_grid_available", "_practice_available", "_meta",
        "_practice_medians", "_weekend_practice", "_weekend_grids", "_testing_data",
    )

    def __init__(self, model_dir: str = "data/models"):
        self._model_dir = model_dir
        # One training at a time: the Predictions page asks for qualifying, race and sprint
        # predictions in parallel, and each used to start its own training on a cold server.
        self._train_lock = asyncio.Lock()
        self._race_model = None
        self._quali_model = None
        self._sprint_model = None
        self._race_features: List[str] = RACE_FEATURES_NO_GRID
        self._quali_features: List[str] = QUALI_FEATURES
        self._sprint_features: List[str] = SPRINT_FEATURES_NO_GRID
        self._practice_available = False
        self._df: Optional[pd.DataFrame] = None
        self._driver_map: Dict[str, str] = {}
        self._constructor_map: Dict[str, str] = {}
        self._le_driver: List[str] = []
        self._le_constructor: List[str] = []
        self._le_circuit: List[str] = []
        self._trained = False
        self._grid_available = False
        self._meta: Dict[str, Any] = {}
        self._practice_medians: Dict[str, float] = {}
        self._testing_data: Dict[int, Dict[str, Any]] = {}     # year -> preseason testing summary
        # Practice already stored for weekends whose race hasn't been run (race_id, year,
        # circuit_name, driver_id + practice columns): used when that race is predicted.
        self._weekend_practice: Optional[pd.DataFrame] = None
        # Qualifying / sprint qualifying already stored for those weekends: a race (sprint) predicted
        # after it starts from the real order, as the backtest's race model does.
        self._weekend_grids: Optional[pd.DataFrame] = None
        # Called (as a task) after every successful training run — main.py uses it to bring the
        # walk-forward backtest up to date once new results have been trained on.
        self.on_trained: Optional[Callable[[], Awaitable[None]]] = None

    @staticmethod
    def data_fingerprint(raw: pd.DataFrame) -> str:
        """Which race results a model or backtest was built from: changes when a race is added
        (or removed), not when the same data is retrained."""
        races = raw[raw["session_type"] == "race"] if "session_type" in raw else raw
        return f"{len(races)}:{int(races['year'].max())}" if not races.empty else "0:0"

    @staticmethod
    def _with_qualifying(df: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
        """Each race row's qualifying result (QUALI_TARGET), else its starting grid."""
        quali = (raw[raw["session_type"] == "qualifying"][["race_id", "driver_id", "position"]]
                 .drop_duplicates(["race_id", "driver_id"]).rename(columns={"position": "quali_position"}))
        # As a rank within the session: an old row stored an unclassified driver at P99 (2026 Australia).
        quali["quali_position"] = quali.groupby("race_id")["quali_position"].rank(method="first")
        df = df.drop(columns=["quali_position", QUALI_TARGET], errors="ignore").merge(quali, on=["race_id", "driver_id"], how="left")
        df[QUALI_TARGET] = df["quali_position"].fillna(df["grid"])
        return df

    @staticmethod
    def _practice_inputs(df: pd.DataFrame) -> List[str]:
        """The practice inputs most rows have (lap times can be missing where ranks aren't)."""
        return [c for c in PRACTICE_INPUTS if c in df and df[c].notna().mean() > 0.5]

    @staticmethod
    def _medians(df: pd.DataFrame) -> Dict[str, float]:
        return {c: float(df[c].median()) for c in PRACTICE_COLUMNS if c in df and df[c].notna().any()}

    @staticmethod
    def _fill_practice(rows: pd.DataFrame, medians: Dict[str, float]) -> pd.DataFrame:
        """Missing practice inputs -> the training medians (a neutral value, unlike the 10 the
        other inputs fall back to)."""
        rows = rows.copy()
        for col in PRACTICE_COLUMNS:
            if col in medians:
                rows[col] = rows[col].fillna(medians[col]) if col in rows else medians[col]
        return rows

    def _notify_trained(self, result: Dict[str, Any]) -> None:
        if result.get("success") and self.on_trained is not None:
            asyncio.create_task(self.on_trained())

    # ------------------------------------------------------------------
    # Label encoding
    # ------------------------------------------------------------------

    def _label_encode(self, series: pd.Series, classes: List[str]) -> pd.Series:
        mapping = {v: i for i, v in enumerate(classes)}
        return series.map(lambda x: mapping.get(x, 0))

    # ------------------------------------------------------------------
    # Model persistence
    # ------------------------------------------------------------------

    def _ensure_model_dir(self):
        os.makedirs(self._model_dir, exist_ok=True)

    def _save_to_disk(self):
        try:
            import joblib
            self._ensure_model_dir()

            if self._race_model is not None:
                joblib.dump(self._race_model, os.path.join(self._model_dir, "race_model.pkl"))
            if self._quali_model is not None:
                joblib.dump(self._quali_model, os.path.join(self._model_dir, "quali_model.pkl"))
            if self._sprint_model is not None:
                joblib.dump(self._sprint_model, os.path.join(self._model_dir, "sprint_model.pkl"))

            joblib.dump(
                {
                    "le_driver": self._le_driver,
                    "le_constructor": self._le_constructor,
                    "le_circuit": self._le_circuit,
                    "driver_map": self._driver_map,
                    "constructor_map": self._constructor_map,
                    "race_features": self._race_features,
                    "quali_features": self._quali_features,
                    "sprint_features": self._sprint_features,
                    "grid_available": self._grid_available,
                },
                os.path.join(self._model_dir, "encoders.pkl"),
            )

            self._meta["saved_at"] = datetime.utcnow().isoformat()
            with open(os.path.join(self._model_dir, "meta.json"), "w") as f:
                json.dump(self._meta, f, indent=2)

            logger.info("✅ Models saved to %s", self._model_dir)
        except Exception as exc:
            logger.error("Failed to save models: %s", exc)

    def load_from_disk(self) -> bool:
        """Load previously trained models from disk. Returns True if successful."""
        try:
            import joblib

            race_path  = os.path.join(self._model_dir, "race_model.pkl")
            enc_path   = os.path.join(self._model_dir, "encoders.pkl")
            meta_path  = os.path.join(self._model_dir, "meta.json")

            if not os.path.exists(enc_path):
                return False

            enc = joblib.load(enc_path)
            self._le_driver       = enc["le_driver"]
            self._le_constructor  = enc["le_constructor"]
            self._le_circuit      = enc["le_circuit"]
            self._driver_map      = enc["driver_map"]
            self._constructor_map = enc["constructor_map"]
            self._race_features   = enc.get("race_features", RACE_FEATURES_NO_GRID)
            self._quali_features  = enc.get("quali_features", QUALI_FEATURES)
            self._sprint_features = enc.get("sprint_features", SPRINT_FEATURES_NO_GRID)
            self._grid_available  = enc.get("grid_available", False)

            if os.path.exists(race_path):
                self._race_model = joblib.load(race_path)

            quali_path = os.path.join(self._model_dir, "quali_model.pkl")
            if os.path.exists(quali_path):
                self._quali_model = joblib.load(quali_path)

            sprint_path = os.path.join(self._model_dir, "sprint_model.pkl")
            if os.path.exists(sprint_path):
                self._sprint_model = joblib.load(sprint_path)

            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    self._meta = json.load(f)

            self._trained = True
            logger.info("✅ Models loaded from disk (trained %s)", self._meta.get("trained_at", "unknown"))
            return True

        except Exception as exc:
            logger.warning("Could not load models from disk: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    async def _load_raw(self, duckdb_service) -> pd.DataFrame:
        rows = await duckdb_service._run_query("""
            SELECT
                rr.race_id, rr.driver_id, rr.constructor_id,
                rr.position, rr.grid, rr.points, rr.status, rr.session_type,
                rr.time,                          -- practice: the driver's best lap
                r.circuit_name, r.year, r.round, r.gp AS race_name,
                d.full_name  AS driver_name,
                c.constructor_name
            FROM race_results rr
            JOIN races r             ON rr.race_id      = r.race_id
            JOIN drivers d           ON rr.driver_id    = d.driver_id
            LEFT JOIN constructors c ON rr.constructor_id = c.constructor_id
            WHERE rr.position IS NOT NULL
            ORDER BY r.year, r.round
        """)
        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        if not df.empty and "session_type" not in df.columns:
            df["session_type"] = "race"  # pre-migration rows with no column at all
        return df

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _engineer(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values(["year", "round"]).copy()

        def roll(s, w=5):
            return s.shift(1).rolling(w, min_periods=1).mean()

        def expand(s):
            return s.expanding().mean().shift(1)

        df["driver_rolling_finish"]      = df.groupby("driver_id")["position"].transform(roll)
        df["driver_rolling_grid"]        = df.groupby("driver_id")["grid"].transform(roll)
        df["driver_circuit_avg"]         = df.groupby(["driver_id", "circuit_name"])["position"].transform(expand)
        df["driver_circuit_grid_avg"]    = df.groupby(["driver_id", "circuit_name"])["grid"].transform(expand)
        df["constructor_rolling_finish"] = df.groupby("constructor_id")["position"].transform(roll)
        df["constructor_circuit_avg"]    = df.groupby(["constructor_id", "circuit_name"])["position"].transform(expand)

        # DNF: anything that isn't "Finished" or "+X laps"
        df["dnf"] = (~df["status"].str.startswith("Finished", na=True) &
                     ~df["status"].str.startswith("+", na=True)).astype(int)
        df["driver_dnf_rate"] = df.groupby("driver_id")["dnf"].transform(
            lambda x: x.shift(1).rolling(10, min_periods=1).mean()
        )

        # Fill NaN with nearest available proxy
        df["driver_circuit_avg"]      = df["driver_circuit_avg"].fillna(df["driver_rolling_finish"])
        df["driver_circuit_grid_avg"] = df["driver_circuit_grid_avg"].fillna(df["driver_rolling_grid"])
        df["constructor_circuit_avg"] = df["constructor_circuit_avg"].fillna(df["constructor_rolling_finish"])
        df["driver_dnf_rate"]         = df["driver_dnf_rate"].fillna(0.1)

        return preseason_testing.apply_testing(add_season_form(df), self._testing_data, TESTING_MODE, TESTING_RACES)

    def _testing_inputs(self) -> List[str]:
        return list(preseason_testing.COLUMNS) if TESTING_MODE.startswith("features") and self._testing_data else []

    async def _load_testing(self, duckdb_service, raw: pd.DataFrame) -> None:
        if raw.empty or "year" not in raw:
            return
        years = sorted({int(y) for y in raw["year"].unique()} | {datetime.utcnow().year})
        self._testing_data = await preseason_testing.load_stored(duckdb_service, years)

    def _encode(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["driver_enc"]      = self._label_encode(df["driver_id"].fillna("unknown"),      self._le_driver)
        df["constructor_enc"] = self._label_encode(df["constructor_id"].fillna("unknown"), self._le_constructor)
        df["circuit_enc"]     = self._label_encode(df["circuit_name"].fillna("unknown"),   self._le_circuit)
        return df

    def _time_weights(self, df: pd.DataFrame) -> np.ndarray:
        """Exponential decay: weight = TIME_DECAY ^ (year - min_year).
        2024 gets ~5× the influence of 2020."""
        min_year = int(df["year"].min())
        return np.array([TIME_DECAY ** (int(y) - min_year) for y in df["year"]], dtype=np.float64)

    # ------------------------------------------------------------------
    # Model construction — kept in one place so backtest/walk-forward
    # evaluation always fits the same shape of model as the live one.
    # ------------------------------------------------------------------

    def _new_ranker(self, lgb):
        """Race, qualifying and sprint models are all the same shape: a ranker
        scored per race, not an absolute-position regressor."""
        return lgb.LGBMRanker(
            n_estimators=300, learning_rate=0.05, max_depth=6,
            num_leaves=31, min_child_samples=5, random_state=42, verbose=-1,
            objective="lambdarank",
        )

    def _fit_ranker(self, lgb, train_df: pd.DataFrame, features: List[str], target_col: str):
        """Fit an LGBMRanker on train_df, if there's enough data. target_col is the raw
        finishing position/grid (lower = better) — converted here to a per-race relevance
        score (higher = better, as LGBMRanker expects: field_size + 1 - value, so last
        place scores ~1 and the winner scores highest) and grouped by race_id, since a
        ranker's loss is defined over which rows in a group should outrank which others.

        field_size must be the TRUE count of classified entries per race, not how many
        rows happen to survive the feature-completeness filter below — otherwise a race
        with even one row dropped for a missing feature (e.g. a driver's first-ever race,
        whose rolling-form features are still NaN) undercounts the field, which can put
        a legitimately low finishing position's relevance below zero. LGBMRanker rejects
        negative labels outright, so this is computed from target_col alone first, then
        clipped to 0 as a floor against any remaining real-world data-quality gaps
        (e.g. a race with fewer ingested rows than its actual grid)."""
        field_size_by_race = train_df.dropna(subset=[target_col]).groupby("race_id")[target_col].transform("count")
        train_df = train_df.assign(_field_size=field_size_by_race)

        train = train_df.dropna(subset=features + [target_col]).sort_values("race_id")
        if len(train) < 20:
            return None

        group = train.groupby("race_id", sort=False).size().to_numpy()
        relevance = (train["_field_size"] + 1 - train[target_col]).clip(lower=0).astype(float)

        model = self._new_ranker(lgb)
        model.fit(
            train[features].astype(float), relevance.values,
            group=group, sample_weight=self._time_weights(train),
        )
        return model

    def _ranks_from_scores(self, scores) -> np.ndarray:
        """A ranker's predict() returns a relevance score (higher = better, arbitrary
        scale) — convert to plain 1..N integer ranks (1 = best) via descending sort.
        Output is aligned to the input order, not sorted."""
        scores = np.asarray(scores)
        order = np.argsort(-scores, kind="stable")
        ranks = np.empty(len(scores), dtype=int)
        ranks[order] = np.arange(1, len(scores) + 1)
        return ranks

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    async def train(self, duckdb_service) -> Dict[str, Any]:
        """Train (or retrain) the models. Serialised: a second caller waits for the first."""
        async with self._train_lock:
            result = await self._train_locked(duckdb_service)
        self._notify_trained(result)
        return result

    async def _train_locked(self, duckdb_service) -> Dict[str, Any]:
        try:
            import lightgbm as lgb
        except ImportError as exc:
            return {"success": False, "error": f"ML packages missing: {exc}. Run: pip install lightgbm"}

        try:
            raw = await self._load_raw(duckdb_service)
            if raw.empty or len(raw) < 20:
                return {"success": False, "error": f"Insufficient data ({len(raw)} rows). Run ingest first."}

            # Fitting is CPU-bound and used to run right on the event loop, stalling every
            # request (including /health) for its whole duration. Run it in a worker thread,
            # on a private copy of the state, and swap the result in when it's done.
            await self._load_testing(duckdb_service, raw)
            scratch = self._scratch_copy()
            result = await asyncio.to_thread(scratch._fit, raw, lgb)
            self._adopt(scratch)
            await duckdb_service.clear_prediction_cache()
            logger.info("Prediction models trained: %s", result)
            return {"success": True, **result}

        except Exception as exc:
            logger.error("Training failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    def _scratch_copy(self) -> "PredictionService":
        scratch = PredictionService(self._model_dir)
        for name in self._FITTED:
            setattr(scratch, name, getattr(self, name))
        return scratch

    def _adopt(self, scratch: "PredictionService") -> None:
        for name in self._FITTED:
            setattr(self, name, getattr(scratch, name))

    def _fit(self, raw: pd.DataFrame, lgb) -> Dict[str, Any]:
        """The CPU-bound part of training. Runs in a worker thread on a scratch copy."""
        years_in_data = sorted(raw["year"].unique().tolist())
        self._driver_map      = raw.drop_duplicates("driver_id").set_index("driver_id")["driver_name"].to_dict()
        self._constructor_map = (raw.dropna(subset=["constructor_id"])
                                    .drop_duplicates("constructor_id")
                                    .set_index("constructor_id")["constructor_name"].to_dict())

        # Sprint rows are pulled out before feature engineering — rolling
        # form / circuit averages are computed from race results only, so
        # a sprint (shorter, different dynamics) never pollutes them.
        raw_race   = raw[raw["session_type"] == "race"].copy()
        raw_sprint = (raw[raw["session_type"] == "sprint"]
                      [["race_id", "driver_id", "position", "grid"]]
                      .rename(columns={"position": "sprint_position", "grid": "sprint_grid"}))
        # Same-weekend practice pace: best rank and gaps (services/practice_features.py).
        raw_practice = practice_features(raw)

        df = self._engineer(raw_race)
        self._le_driver      = sorted(df["driver_id"].fillna("unknown").unique().tolist())
        self._le_constructor = sorted(df["constructor_id"].fillna("unknown").unique().tolist())
        self._le_circuit     = sorted(df["circuit_name"].fillna("unknown").unique().tolist())
        df = self._encode(df)

        # Attach each weekend's sprint result (if any) onto that weekend's
        # already-engineered race-form row — same driver/constructor state
        # going into the weekend, just a different target to predict.
        if not raw_sprint.empty:
            df = df.merge(raw_sprint, on=["race_id", "driver_id"], how="left")
        else:
            df["sprint_position"] = np.nan
            df["sprint_grid"] = np.nan

        df = df.merge(raw_practice, on=["race_id", "driver_id"], how="left")
        df = self._with_qualifying(df, raw)
        self._df = df
        self._practice_medians = self._medians(df)
        weekends = (raw[~raw["race_id"].isin(raw_race["race_id"])]
                    .drop_duplicates("race_id")[["race_id", "year", "circuit_name"]])
        self._weekend_practice = raw_practice.merge(weekends, on="race_id")
        self._weekend_grids = (raw[raw["session_type"].isin(["qualifying", "sprint_qualifying"])
                                   & ~raw["race_id"].isin(raw_race["race_id"])]
                               [["race_id", "year", "circuit_name", "session_type", "driver_id", "position"]])

        result: Dict[str, Any] = {
            "rows": len(df),
            "years": years_in_data,
            "decay_factor": TIME_DECAY,
        }

        # Same >0.5 convention as grid_coverage below: only trust the feature once
        # most rows actually have it, so early/sparse practice ingest can't silently
        # degrade training with a mostly-missing column.
        practice_coverage = df["driver_practice_best_rank"].notna().mean()
        self._practice_available = bool(practice_coverage > 0.5)
        result["practice_coverage"] = f"{practice_coverage:.0%}"
        practice_feat = self._practice_inputs(df) if self._practice_available else []

        # ---- Race model ----
        grid_coverage = df["grid"].notna().mean()
        self._grid_available  = bool(grid_coverage > 0.5)
        self._race_features   = (RACE_FEATURES_FULL if self._grid_available else RACE_FEATURES_NO_GRID) + practice_feat + self._testing_inputs()
        result["grid_coverage"] = f"{grid_coverage:.0%}"

        self._race_model = self._fit_ranker(lgb, df, self._race_features, "position")
        if self._race_model is not None:
            result["race_training_rows"] = len(df.dropna(subset=self._race_features + ["position"]))
        else:
            result["race_model"] = "skipped — not enough complete rows"

        # ---- Qualifying model ----
        self._quali_features = QUALI_FEATURES + practice_feat + self._testing_inputs()
        self._quali_model = self._fit_ranker(lgb, df, self._quali_features, QUALI_TARGET)
        result["quali_target_coverage"] = f"{df['quali_position'].notna().mean():.0%}"   # the rest use the grid
        if self._quali_model is not None:
            result["quali_training_rows"] = len(df.dropna(subset=self._quali_features + [QUALI_TARGET]))
        else:
            result["quali_model"] = "skipped — grid column is NULL. Re-ingest data to populate grid positions."

        # ---- Sprint model ----
        # Sprints are much rarer than full races (roughly half a dozen a
        # season, only since 2021), so this trains on far fewer rows than
        # the race model — expect lower confidence until more are ingested.
        sprint_grid_coverage = df["sprint_grid"].notna().mean() if df["sprint_position"].notna().any() else 0.0
        sprint_grid_available = bool(sprint_grid_coverage > 0.5)
        self._sprint_features = (SPRINT_FEATURES_FULL if sprint_grid_available else SPRINT_FEATURES_NO_GRID) + practice_feat
        result["sprint_grid_coverage"] = f"{sprint_grid_coverage:.0%}"

        sprint_row_count = len(df.dropna(subset=self._sprint_features + ["sprint_position"]))
        self._sprint_model = self._fit_ranker(lgb, df, self._sprint_features, "sprint_position")
        if self._sprint_model is not None:
            result["sprint_training_rows"] = sprint_row_count
        else:
            result["sprint_model"] = f"skipped — only {sprint_row_count} historical sprint rows (need 20+). Ingest more sprint weekends."

        self._trained = True
        self._meta = {
            "trained_at": datetime.utcnow().isoformat(),
            "rows": len(df),
            "years": years_in_data,
            "decay_factor": TIME_DECAY,
            "data_fingerprint": self.data_fingerprint(raw),
            "grid_coverage": result["grid_coverage"],
            "practice_coverage": result["practice_coverage"],
            "race_model_ready": self._race_model is not None,
            "quali_model_ready": self._quali_model is not None,
            "sprint_model_ready": self._sprint_model is not None,
        }

        self._save_to_disk()
        return result

    # ------------------------------------------------------------------
    # Feature rows for a future race at a given circuit
    # ------------------------------------------------------------------

    # Driver inputs a debutant gets: the field's median (the team's form still comes from the team).
    _DRIVER_INPUTS = ("grid", "driver_rolling_finish", "driver_circuit_avg", "driver_dnf_rate",
                      "driver_rolling_grid", "driver_circuit_grid_avg", "driver_season_avg_grid")

    def _build_prediction_rows(self, circuit_name: str, df: Optional[pd.DataFrame] = None,
                               field: Optional[Dict[str, Optional[str]]] = None,
                               season: Optional[int] = None, use_testing: bool = True) -> pd.DataFrame:
        """One feature row per driver for a race at `circuit_name`.

        `field` is who's actually entered, driver_id -> constructor_id (None: their last team) —
        see services/entry_list.py. Without it the field is the latest race's line-up, which
        misses a driver returning (e.g. from injury) and keeps one who's out. `df` is the history
        to build from — the full training frame by default; the championship backtest passes
        history cut off at an earlier round. `season` is the race's season (default: this year for
        the live frame), which says whether season-to-date form starts from nothing."""
        df = self._df if df is None else df
        if field is None:
            most_recent_year = int(df["year"].max())
            latest_round = int(df.loc[df["year"] == most_recent_year, "round"].max())
            drivers = list(df[(df["year"] == most_recent_year) & (df["round"] == latest_round)]["driver_id"].unique())
        else:
            drivers = list(field)
        df_recent = df[df["driver_id"].isin(drivers)]
        latest = df_recent.sort_values(["year", "round"]).groupby("driver_id").last().reset_index()

        circuit_round_series = df[df["circuit_name"] == circuit_name]["round"]
        circuit_round = int(circuit_round_series.mode().iloc[0]) if not circuit_round_series.empty else 1

        # Season form going into the race: after the latest race, or nothing yet in a new season.
        latest_year = int(df["year"].max())
        season = season or (datetime.utcnow().year if df is self._df else latest_year)
        new_season = season > latest_year
        team_points = {} if new_season else team_points_after(df, latest_year).to_dict()

        rows = []
        for _, r in latest.iterrows():
            cir_d = df[(df["driver_id"]      == r["driver_id"])      & (df["circuit_name"] == circuit_name)]
            cir_c = df[(df["constructor_id"] == r["constructor_id"]) & (df["circuit_name"] == circuit_name)]

            rows.append({
                "driver_id":               r["driver_id"],
                "constructor_id":          r.get("constructor_id", "unknown"),
                "circuit_name":            circuit_name,
                "grid":                    float(r.get("grid") or r.get("driver_rolling_grid") or 10),
                "driver_rolling_finish":   float(r.get("driver_rolling_finish")    or 10),
                "driver_circuit_avg":      float(cir_d["position"].mean()) if not cir_d.empty else float(r.get("driver_rolling_finish") or 10),
                "constructor_rolling_finish": float(r.get("constructor_rolling_finish") or 10),
                "constructor_circuit_avg": float(cir_c["position"].mean()) if not cir_c.empty else float(r.get("constructor_rolling_finish") or 10),
                "driver_dnf_rate":         float(r.get("driver_dnf_rate") or 0.1),
                "driver_rolling_grid":     float(r.get("driver_rolling_grid")      or 10),
                "driver_circuit_grid_avg": float(cir_d["grid"].mean()) if not cir_d.empty and cir_d["grid"].notna().any() else float(r.get("driver_rolling_grid") or 10),
                "driver_season_points":    0.0 if new_season or int(r["year"]) != latest_year
                                           else float(r.get("driver_season_points_after") or 0),
                "driver_season_avg_grid":  float(r.get("driver_season_avg_grid_after") or r.get("driver_rolling_grid") or 10),
                "team_season_points":      float(team_points.get(r.get("constructor_id"), 0.0)),
                # Practice is filled in below: this weekend's, if it's been stored, else neutral.
                "round": circuit_round,
            })

        out = pd.DataFrame(rows)
        # Races into the season this one is: the new season's first, or the next after the latest.
        race_no = 1 if new_season else int(df.loc[df["year"] == latest_year, "round"].nunique()) + 1
        if field is None:
            out = self._with_testing(out, season, race_no) if use_testing else out
            return self._with_practice(out, circuit_name, live=df is self._df)

        # Entered drivers with no history at all (a debut): the field's typical driver inputs.
        known = set(out["driver_id"]) if not out.empty else set()
        debutants = [d for d in drivers if d not in known]
        if debutants:
            typical = out[list(self._DRIVER_INPUTS)].median() if not out.empty else pd.Series(10.0, index=self._DRIVER_INPUTS)
            out = pd.concat([out, pd.DataFrame([{
                "driver_id": d, "constructor_id": field.get(d) or "unknown", "circuit_name": circuit_name,
                **typical.to_dict(), "driver_season_points": 0.0, "round": circuit_round,
            } for d in debutants])], ignore_index=True)
        out = self._with_teams(out, {d: t for d, t in field.items() if t}, df, circuit_name, team_points)
        out = self._with_testing(out, season, race_no) if use_testing else out
        return self._with_practice(out, circuit_name, live=df is self._df)

    def _with_testing(self, rows: pd.DataFrame, season: int, race_no: int) -> pd.DataFrame:
        if TESTING_MODE != "rule":
            return rows
        return preseason_testing.apply_to_upcoming(rows, self._testing_data, season, race_no, TESTING_RACES)

    def weekend_practice(self, circuit_name: str) -> Optional[pd.DataFrame]:
        """Practice stored for the coming race at `circuit_name` (its race not run yet), if any."""
        wp = self._weekend_practice
        if wp is None or wp.empty or self._df is None:
            return None
        rows = wp[(wp["circuit_name"] == circuit_name) & (wp["year"] == wp["year"].max())]
        return rows if not rows.empty else None

    def weekend_grid(self, circuit_name: str, session_type: str) -> Optional[Dict[str, int]]:
        """driver_id -> position in the coming race's stored qualifying (or sprint qualifying)."""
        g = self._weekend_grids
        if g is None or g.empty or self._df is None:
            return None
        rows = g[(g["circuit_name"] == circuit_name) & (g["session_type"] == session_type) & (g["year"] == g["year"].max())]
        return {d: int(p) for d, p in zip(rows["driver_id"], rows["position"])} if len(rows) else None

    def _starting_order(self, feat: pd.DataFrame, circuit_name: str, session_type: str) -> tuple:
        """The grid a race (sprint) prediction starts from: the stored qualifying order where there
        is one (drivers it doesn't cover go after, in predicted order), else the predicted one.
        Returns (ranks, where they came from)."""
        feat_q = self._encode(feat.copy())
        predicted = self._ranks_from_scores(self._quali_model.predict(feat_q[self._quali_features].fillna(10)))
        actual = self.weekend_grid(circuit_name, session_type)
        if not actual:
            return predicted, None
        known = feat["driver_id"].map(actual)
        order = sorted(range(len(feat)), key=lambda i: (pd.isna(known.iloc[i]), known.iloc[i] if pd.notna(known.iloc[i]) else 0, predicted[i]))
        ranks = np.empty(len(feat), dtype=int)
        ranks[order] = np.arange(1, len(feat) + 1)
        label = "sprint qualifying" if session_type == "sprint_qualifying" else "qualifying"
        return ranks, f"this weekend's {label}"

    def _with_practice(self, rows: pd.DataFrame, circuit_name: str, live: bool) -> pd.DataFrame:
        if rows.empty:
            return rows
        rows = rows.drop(columns=[c for c in PRACTICE_COLUMNS if c in rows])
        practice = self.weekend_practice(circuit_name) if live else None
        if practice is not None:
            rows = rows.merge(practice[["driver_id"] + PRACTICE_COLUMNS], on="driver_id", how="left")
        else:
            rows = rows.assign(**{c: np.nan for c in PRACTICE_COLUMNS})
        return self._fill_practice(rows, self._practice_medians)

    def _with_teams(self, rows: pd.DataFrame, teams: Dict[str, str], history: pd.DataFrame,
                    circuit_name: str, team_points: Optional[Dict[str, float]] = None) -> pd.DataFrame:
        """A driver in a different car from their last history row races the new car: give them
        that team's form (Sainz at Williams in 2025, not Ferrari; a debutant's team)."""
        if rows.empty or not teams:
            return rows
        rows = rows.copy()
        team_form = history.sort_values(["year", "round"]).groupby("constructor_id")["constructor_rolling_finish"].last()
        for i, row in rows.iterrows():
            team = teams.get(row["driver_id"])
            if not team or (team == row["constructor_id"] and pd.notna(row.get("constructor_rolling_finish"))):
                continue
            at_circuit = history.loc[(history["constructor_id"] == team) & (history["circuit_name"] == circuit_name), "position"]
            form = team_form.get(team, np.nan)
            rows.at[i, "constructor_id"] = team
            rows.at[i, "constructor_rolling_finish"] = form
            rows.at[i, "constructor_circuit_avg"] = at_circuit.mean() if not at_circuit.empty else form
            if team_points is not None:
                rows.at[i, "team_season_points"] = float(team_points.get(team, 0.0))
        return rows

    # ------------------------------------------------------------------
    # Public predict API
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_usable(cached: Optional[Dict[str, Any]], trained_at: Optional[str],
                      field: Optional[Dict[str, Optional[str]]] = None, need_scores: bool = True) -> bool:
        """A cached prediction from the current model, in the current shape (with scores — rows
        cached before scores were kept are recomputed once), for the same drivers in the same
        cars (the entry list can change between sessions of a weekend)."""
        if not cached or cached.get("model_trained_at") != trained_at:
            return False
        preds = cached.get("result", {}).get("predictions") or []
        if not preds or (need_scores and "score" not in preds[0]) or "field_source" not in cached["result"]:
            return False
        if field is None:
            return True
        return ({p["driver_id"] for p in preds} == set(field)
                and all(field[p["driver_id"]] in (None, p.get("constructor_id")) for p in preds))

    async def _ensure_trained(self, duckdb_service):
        # Also retrain if df is missing (e.g. loaded from disk but df not persisted)
        if self._trained and self._df is not None:
            return
        # Single-flight: concurrent callers (three predictions in parallel, or the startup
        # warm-up) wait here for the one training instead of each starting their own.
        async with self._train_lock:
            if self._trained and self._df is not None:
                return  # someone finished while we waited
            if self.load_from_disk() and self._df is not None:
                return
            result = await self._train_locked(duckdb_service)
        self._notify_trained(result)

    async def predict_qualifying(self, circuit_name: str, duckdb_service,
                        field: Optional[Dict[str, Optional[str]]] = None, field_source: Optional[str] = None) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._quali_model is None:
            return {
                "success": False,
                "error": "Qualifying model unavailable — grid data is missing. Re-ingest 2020–2024 data to populate grid positions.",
                "predictions": [],
            }

        trained_at = self._meta.get("trained_at")
        cached = await duckdb_service.get_prediction_cache(circuit_name, "qualifying")
        if self._cache_usable(cached, trained_at, field):
            return cached["result"]

        feat  = self._build_prediction_rows(circuit_name, field=field)
        feat  = self._encode(feat)
        preds = self._quali_model.predict(feat[self._quali_features].fillna(10))
        feat["score"] = preds
        feat["predicted_grid"] = self._ranks_from_scores(preds)
        feat  = feat.sort_values("predicted_grid").reset_index(drop=True)

        output = []
        for rank, row in feat.iterrows():
            output.append({
                "predicted_rank":   rank + 1,
                "driver_id":        row["driver_id"],
                "driver_name":      self._driver_map.get(row["driver_id"], row["driver_id"]),
                "constructor_id":   row["constructor_id"],
                "constructor_name": self._constructor_map.get(row["constructor_id"], row["constructor_id"]),
                "predicted_grid":   int(row["predicted_grid"]),
                "score":            round(float(row["score"]), 6),
                "circuit_avg_grid": round(float(row["driver_circuit_grid_avg"]), 2) if pd.notna(row.get("driver_circuit_grid_avg")) else None,
                "rolling_avg_grid": round(float(row["driver_rolling_grid"]), 2)     if pd.notna(row.get("driver_rolling_grid"))      else None,
            })

        result = {
            "success": True,
            "circuit": circuit_name,
            "model": "LightGBM (ranker)",
            "grid_data_available": self._grid_available,
            "field_source": field_source or "the last race's line-up",
            "practice_used": self.weekend_practice(circuit_name) is not None,
            "predictions": output,
        }
        await duckdb_service.set_prediction_cache(circuit_name, "qualifying", trained_at, result)
        return result

    async def predict_race(self, circuit_name: str, duckdb_service,
                        field: Optional[Dict[str, Optional[str]]] = None, field_source: Optional[str] = None) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._race_model is None:
            return {"success": False, "error": "Race model unavailable.", "predictions": []}

        trained_at = self._meta.get("trained_at")
        cached = await duckdb_service.get_prediction_cache(circuit_name, "race")
        if self._cache_usable(cached, trained_at, field):
            return cached["result"]

        feat = self._build_prediction_rows(circuit_name, field=field)

        # Pipe qualifying predictions in as the grid input — as a rank (1..N), the same
        # scale the race model's own "grid" training column is on, not the ranker's raw
        # relevance score (an arbitrary scale the race model was never trained on).
        grid_source = None
        if self._quali_model is not None:
            feat["grid"], grid_source = self._starting_order(feat, circuit_name, "qualifying")

        feat  = self._encode(feat)
        preds = self._race_model.predict(feat[self._race_features].fillna(10))
        feat["score"] = preds
        feat["predicted_position"] = self._ranks_from_scores(preds)
        feat  = feat.sort_values("predicted_position").reset_index(drop=True)

        output = []
        for rank, row in feat.iterrows():
            output.append({
                "predicted_rank":     rank + 1,
                "driver_id":          row["driver_id"],
                "driver_name":        self._driver_map.get(row["driver_id"], row["driver_id"]),
                "constructor_id":     row["constructor_id"],
                "constructor_name":   self._constructor_map.get(row["constructor_id"], row["constructor_id"]),
                "predicted_position": int(row["predicted_position"]),
                "score":              round(float(row["score"]), 6),
                "circuit_avg_finish": round(float(row["driver_circuit_avg"]), 2)      if pd.notna(row.get("driver_circuit_avg"))      else None,
                "rolling_avg_finish": round(float(row["driver_rolling_finish"]), 2)   if pd.notna(row.get("driver_rolling_finish"))   else None,
                "predicted_grid":     int(row["grid"]),
                "dnf_rate":           round(float(row["driver_dnf_rate"]), 4) if pd.notna(row.get("driver_dnf_rate")) else None,
            })

        result = {
            "success": True,
            "circuit": circuit_name,
            "model": "LightGBM (ranker)",
            "grid_data_available": self._grid_available,
            "field_source": field_source or "the last race's line-up",
            "practice_used": self.weekend_practice(circuit_name) is not None,
            "grid_source": grid_source or "predicted qualifying",   # where the starting order came from
            "predictions": output,
        }
        await duckdb_service.set_prediction_cache(circuit_name, "race", trained_at, result)
        return result

    async def predict_sprint(self, circuit_name: str, duckdb_service,
                        field: Optional[Dict[str, Optional[str]]] = None, field_source: Optional[str] = None) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._sprint_model is None:
            return {
                "success": False,
                "error": "Sprint model unavailable — not enough historical sprint results ingested yet.",
                "predictions": [],
            }

        trained_at = self._meta.get("trained_at")
        cached = await duckdb_service.get_prediction_cache(circuit_name, "sprint")
        if self._cache_usable(cached, trained_at, field):
            return cached["result"]

        feat = self._build_prediction_rows(circuit_name, field=field)

        # No separate sprint-qualifying model (too little data to train one
        # reliably) — the main qualifying model's prediction is used as a
        # proxy for sprint grid, since both measure one-lap pace. As a rank
        # (1..N), same scale the sprint model's own "sprint_grid" column is on.
        grid_source = None
        if self._quali_model is not None:
            feat["sprint_grid"], grid_source = self._starting_order(feat, circuit_name, "sprint_qualifying")
        else:
            feat["sprint_grid"] = feat.get("grid", 10)

        feat  = self._encode(feat)
        preds = self._sprint_model.predict(feat[self._sprint_features].fillna(10))
        feat["score"] = preds
        feat["predicted_position"] = self._ranks_from_scores(preds)
        feat  = feat.sort_values("predicted_position").reset_index(drop=True)

        output = []
        for rank, row in feat.iterrows():
            output.append({
                "predicted_rank":     rank + 1,
                "driver_id":          row["driver_id"],
                "driver_name":        self._driver_map.get(row["driver_id"], row["driver_id"]),
                "constructor_id":     row["constructor_id"],
                "constructor_name":   self._constructor_map.get(row["constructor_id"], row["constructor_id"]),
                "predicted_position": int(row["predicted_position"]),
                "circuit_avg_finish": round(float(row["driver_circuit_avg"]), 2)      if pd.notna(row.get("driver_circuit_avg"))      else None,
                "rolling_avg_finish": round(float(row["driver_rolling_finish"]), 2)   if pd.notna(row.get("driver_rolling_finish"))   else None,
                "predicted_grid":     int(row["sprint_grid"]),
                "score":              round(float(row["score"]), 6),
                "dnf_rate":           round(float(row["driver_dnf_rate"]), 4) if pd.notna(row.get("driver_dnf_rate")) else None,
            })

        result = {
            "success": True,
            "circuit": circuit_name,
            "model": "LightGBM (ranker, sprint)",
            "grid_data_available": self._grid_available,
            "field_source": field_source or "the last race's line-up",
            "practice_used": self.weekend_practice(circuit_name) is not None,
            "grid_source": grid_source or "predicted qualifying",   # where the starting order came from
            "predictions": output,
        }
        await duckdb_service.set_prediction_cache(circuit_name, "sprint", trained_at, result)
        return result

    # ------------------------------------------------------------------
    # Backtest: predicted vs actual for real past races
    # ------------------------------------------------------------------

    def _score_group(self, group: pd.DataFrame, quali_model, race_model,
                      race_features: List[str], quali_features: List[str],
                      practice_medians: Optional[Dict[str, float]] = None,
                      sprint_model=None, sprint_features: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Score one race's rows against a given model pair. Used by both backtest()
        (the live model) and walk_forward_backtest() (a season-scoped scratch model) —
        takes the models as arguments rather than reading self._quali_model/self._race_model
        so the two callers can pass different ones."""
        drivers: Dict[str, Dict[str, Any]] = {}
        if practice_medians:
            practice_data = bool(group["driver_practice_best_rank"].notna().mean() > 0.5) if "driver_practice_best_rank" in group else False
            group = self._fill_practice(group, practice_medians)
        else:
            practice_data = None

        # Practice pace is optional here: a weekend without stored practice is scored with it
        # missing (filled like any missing input, the way an upcoming race is predicted) rather
        # than dropped, and flagged, so recent races don't vanish from the accuracy tab.
        def required(features: List[str]) -> List[str]:
            return [f for f in features if f not in PRACTICE_COLUMNS]

        if quali_model is not None:
            qdf = group.dropna(subset=required(quali_features) + [QUALI_TARGET])
            if not qdf.empty:
                scores = quali_model.predict(qdf[quali_features].fillna(10))
                ranks = self._ranks_from_scores(scores)
                for (_, row), rank, score in zip(qdf.iterrows(), ranks, scores):
                    d = drivers.setdefault(row["driver_id"], {
                        "driver_id": row["driver_id"],
                        "driver_name": self._driver_map.get(row["driver_id"], row["driver_id"]),
                    })
                    d["predicted_grid"] = int(rank)
                    d["quali_score"] = round(float(score), 5)   # for the odds (services/backtest_scores.py)
                    d["actual_quali"] = int(row[QUALI_TARGET])
                    d["actual_grid"] = int(row["grid"]) if pd.notna(row["grid"]) else None

        if race_model is not None:
            rdf = group.dropna(subset=required(race_features) + ["position"])
            if not rdf.empty:
                scores = race_model.predict(rdf[race_features].fillna(10))
                ranks = self._ranks_from_scores(scores)
                for (_, row), rank, score in zip(rdf.iterrows(), ranks, scores):
                    d = drivers.setdefault(row["driver_id"], {
                        "driver_id": row["driver_id"],
                        "driver_name": self._driver_map.get(row["driver_id"], row["driver_id"]),
                    })
                    d["predicted_position"] = int(rank)
                    d["race_score"] = round(float(score), 5)
                    d["actual_position"] = int(row["position"]) if pd.notna(row["position"]) else None
                    d["status"] = str(row["status"]) if pd.notna(row.get("status")) else None   # retirements, for the odds
                    d["dnf_rate"] = round(float(row["driver_dnf_rate"]), 4) if pd.notna(row.get("driver_dnf_rate")) else None
                    d.setdefault("actual_grid", int(row["grid"]) if pd.notna(row["grid"]) else None)

        if sprint_model is not None and sprint_features and "sprint_position" in group:
            sdf = group.dropna(subset=required(sprint_features) + ["sprint_position"])
            if len(sdf) >= 2:
                scores = sprint_model.predict(sdf[sprint_features].fillna(10))
                ranks = self._ranks_from_scores(scores)
                for (_, row), rank, score in zip(sdf.iterrows(), ranks, scores):
                    d = drivers.setdefault(row["driver_id"], {
                        "driver_id": row["driver_id"],
                        "driver_name": self._driver_map.get(row["driver_id"], row["driver_id"]),
                    })
                    d["predicted_sprint"] = int(rank)
                    d["sprint_score"] = round(float(score), 5)
                    d["actual_sprint"] = int(row["sprint_position"])
                    d["sprint_grid"] = int(row["sprint_grid"]) if pd.notna(row.get("sprint_grid")) else None

        if not drivers:
            return None

        # The championship order going into the weekend (a baseline for services/backtest_scores.py):
        # Grand Prix points so far this season, recent form breaking ties (round 1: all on 0).
        if "driver_season_points" in group:
            standing = group.sort_values(["driver_season_points", "driver_rolling_finish"], ascending=[False, True])
            for rank, driver_id in enumerate(standing["driver_id"], start=1):
                if driver_id in drivers:
                    drivers[driver_id]["standings_rank"] = rank

        driver_rows = sorted(drivers.values(), key=lambda d: d.get("actual_position") or 99)

        quali_errs = [abs(d["predicted_grid"] - d["actual_quali"]) for d in driver_rows
                      if d.get("predicted_grid") is not None and d.get("actual_quali") is not None]
        race_errs = [abs(d["predicted_position"] - d["actual_position"]) for d in driver_rows
                     if d.get("predicted_position") is not None and d.get("actual_position") is not None]
        sprint_errs = [abs(d["predicted_sprint"] - d["actual_sprint"]) for d in driver_rows
                       if d.get("predicted_sprint") is not None and d.get("actual_sprint") is not None]

        return {
            "year": int(group["year"].iloc[0]),
            "round": int(group["round"].iloc[0]),
            "race_id": group["race_id"].iloc[0],
            "race_name": group["race_name"].iloc[0],
            "circuit_name": group["circuit_name"].iloc[0],
            "quali_mae": round(sum(quali_errs) / len(quali_errs), 2) if quali_errs else None,
            "race_mae": round(sum(race_errs) / len(race_errs), 2) if race_errs else None,
            "sprint_mae": round(sum(sprint_errs) / len(sprint_errs), 2) if sprint_errs else None,
            # Whether the practice-pace input was known for this weekend (None: not a model input).
            "practice_data": ((practice_data if practice_data is not None
                               else bool(group["driver_practice_best_rank"].notna().mean() > 0.5))
                              if "driver_practice_best_rank" in set(race_features) | set(quali_features) else None),
            "drivers": driver_rows,
        }

    def _score_races(self, df: pd.DataFrame, quali_model, race_model,
                      race_features: List[str], quali_features: List[str],
                      practice_medians: Optional[Dict[str, float]] = None,
                      sprint_model=None, sprint_features: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        races_out = []
        for _, group in df.groupby(["year", "round", "race_id"], sort=False):
            race = self._score_group(group, quali_model, race_model, race_features, quali_features, practice_medians,
                                     sprint_model, sprint_features)
            if race is not None:
                races_out.append(race)
        return races_out

    def backtest(self, years_back: int = 3) -> Dict[str, Any]:
        """Score the current models against real results from the last
        `years_back` seasons.

        Each row in self._df already has point-in-time-correct features —
        _engineer() builds driver/constructor rolling and circuit averages
        with .shift(1) before rolling/expanding, so a given race's row only
        reflects races before it, never after. That means running these
        historical rows back through the model isn't affected by feature
        leakage. The one caveat: the models themselves were fit once on the
        full dataset (time-decayed, not walk-forward retrained per race), so
        this is a retrospective scoring of the current model rather than a
        strict walk-forward backtest. walk_forward_backtest() below is the
        strict version; GET /predict/backtest prefers its cached result and
        only falls back to this method when no walk-forward result exists yet.
        """
        if self._df is None or self._df.empty:
            return {"races": []}

        cutoff_year = datetime.utcnow().year - years_back
        df = self._df[self._df["year"] >= cutoff_year]
        if df.empty:
            return {"races": []}

        races_out = self._score_races(df, self._quali_model, self._race_model, self._race_features,
                                      self._quali_features, self._practice_medians)
        races_out.sort(key=lambda r: (r["year"], r["round"]), reverse=True)
        return {"races": races_out}

    # ------------------------------------------------------------------
    # Walk-forward backtest: every race is scored by a model that never saw
    # it — an honest holdout, unlike backtest() above which scores the live
    # model against history it was fit on.
    # ------------------------------------------------------------------

    # Bump when the backtest's method changes, so every cached unit is recomputed.
    WALK_FORWARD_VERSION = "9"

    async def walk_forward_backtest(self, duckdb_service, years_back: int = 3,
                                    previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Earlier seasons are each scored by one model trained on the seasons before them; the
        latest season race by race, each round by a model trained on everything up to the round
        before — what the live site actually does, since it retrains after every race. Units whose
        inputs haven't changed are taken from `previous` (the cached result), so a new race costs
        one refit. Expensive the first time; run it in the background and cache the result."""
        raw = await self._load_raw(duckdb_service)
        if raw.empty or len(raw) < 20:
            return {"races": [], "error": f"Insufficient data ({len(raw)} rows)"}

        try:
            import lightgbm as lgb
        except ImportError as exc:
            return {"races": [], "error": f"ML packages missing: {exc}"}

        await self._load_testing(duckdb_service, raw)
        return await asyncio.to_thread(self._walk_forward_fit, raw, lgb, years_back, previous)

    @staticmethod
    def _unit_fingerprint(rows: pd.DataFrame, features: List[str], extra: str) -> str:
        """What a scoring unit's result depends on: its training and test rows' model inputs and
        targets, the feature list and the method version."""
        cols = ["year", "round", "race_id", "driver_id"] + [c for c in features if c not in ("year", "round")] + ["position", "grid", QUALI_TARGET, "sprint_position", "sprint_grid"]
        cols = list(dict.fromkeys(c for c in cols if c in rows.columns))
        ordered = rows.sort_values(["year", "round", "driver_id"])[cols]
        digest = hashlib.sha1(pd.util.hash_pandas_object(ordered, index=False).values.tobytes())
        digest.update("|".join(features + [extra, str(TIME_DECAY), PredictionService.WALK_FORWARD_VERSION]).encode())
        return digest.hexdigest()[:16]

    def _walk_forward_fit(self, raw: pd.DataFrame, lgb, years_back: int,
                          previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raw_race = raw[raw["session_type"] == "race"].copy()
        if raw_race.empty:
            return {"races": []}
        # Names for the scored rows: a service that hasn't trained yet has no name map, and the
        # results would show driver codes ("ant") instead.
        if "driver_name" in raw_race:
            names = raw_race.dropna(subset=["driver_name"]).drop_duplicates("driver_id", keep="last")
            self._driver_map = {**names.set_index("driver_id")["driver_name"].to_dict(), **self._driver_map}

        raw_practice = practice_features(raw)

        # Feature engineering runs over the whole history at once — safe because every
        # rolling/expanding feature already uses .shift(1), so a row's features only ever
        # reflect races strictly before it regardless of what else is in the frame. What
        # actually gets walked forward is which rows each model is FIT on, below.
        df = self._engineer(raw_race)
        le_driver      = sorted(df["driver_id"].fillna("unknown").unique().tolist())
        le_constructor = sorted(df["constructor_id"].fillna("unknown").unique().tolist())
        le_circuit     = sorted(df["circuit_name"].fillna("unknown").unique().tolist())
        df["driver_enc"]      = self._label_encode(df["driver_id"].fillna("unknown"), le_driver)
        df["constructor_enc"] = self._label_encode(df["constructor_id"].fillna("unknown"), le_constructor)
        df["circuit_enc"]     = self._label_encode(df["circuit_name"].fillna("unknown"), le_circuit)

        df = df.merge(raw_practice, on=["race_id", "driver_id"], how="left")
        df = self._with_qualifying(df, raw)
        raw_sprint = (raw[raw["session_type"] == "sprint"][["race_id", "driver_id", "position", "grid"]]
                      .drop_duplicates(["race_id", "driver_id"])
                      .rename(columns={"position": "sprint_position", "grid": "sprint_grid"}))
        df = df.merge(raw_sprint, on=["race_id", "driver_id"], how="left")

        all_years = sorted(df["year"].unique().tolist())
        if len(all_years) < 2:
            return {"races": []}

        current_year = datetime.utcnow().year
        test_years = [y for y in all_years if y > all_years[0] and y >= current_year - years_back]
        latest_year = all_years[-1]

        grid_available = bool(df["grid"].notna().mean() > 0.5)
        practice_available = bool(df["driver_practice_best_rank"].notna().mean() > 0.5)
        practice_feat = self._practice_inputs(df) if practice_available else []
        race_features = (RACE_FEATURES_FULL if grid_available else RACE_FEATURES_NO_GRID) + practice_feat + self._testing_inputs()
        quali_features = QUALI_FEATURES + practice_feat + self._testing_inputs()
        sprints = df.dropna(subset=["sprint_position"])
        sprint_grid_ok = bool(len(sprints)) and bool(sprints["sprint_grid"].notna().mean() > 0.5)
        sprint_features = (SPRINT_FEATURES_FULL if sprint_grid_ok else SPRINT_FEATURES_NO_GRID) + practice_feat

        # Scoring units: (id, rows the model is fit on, rows it's scored on).
        units = []
        for test_year in test_years:
            if test_year == latest_year:
                season = df[df["year"] == test_year]
                for rnd in sorted(int(r) for r in season["round"].unique()):
                    train = df[(df["year"] < test_year) | ((df["year"] == test_year) & (df["round"] < rnd))]
                    units.append((f"{test_year}-r{rnd}", train, season[season["round"] == rnd]))
            else:
                units.append((str(test_year), df[df["year"] < test_year], df[df["year"] == test_year]))

        cached_units = (previous or {}).get("units") or {}
        cached_races: Dict[str, List[Dict[str, Any]]] = {}
        for race in (previous or {}).get("races") or []:
            if race.get("unit"):
                cached_races.setdefault(race["unit"], []).append(race)

        all_features = list(dict.fromkeys(race_features + quali_features + sprint_features))
        races_out: List[Dict[str, Any]] = []
        units_out: Dict[str, Dict[str, Any]] = {}
        refits = 0
        for unit_id, train_df, test_df in units:
            if test_df.empty:
                continue
            fingerprint = self._unit_fingerprint(pd.concat([train_df, test_df]), all_features,
                                                 f"{unit_id}:{len(train_df)}")
            if cached_units.get(unit_id, {}).get("fingerprint") == fingerprint and unit_id in cached_races:
                scored = cached_races[unit_id]
            else:
                race_model  = self._fit_ranker(lgb, train_df, race_features, "position")
                quali_model = self._fit_ranker(lgb, train_df, quali_features, QUALI_TARGET)
                sprint_model = (self._fit_ranker(lgb, train_df, sprint_features, "sprint_position")
                                if test_df["sprint_position"].notna().any() else None)
                refits += 1
                if race_model is None and quali_model is None:
                    continue
                scored = [{**r, "unit": unit_id}
                          for r in self._score_races(test_df, quali_model, race_model, race_features, quali_features,
                                                     self._medians(train_df), sprint_model, sprint_features)]
            units_out[unit_id] = {"fingerprint": fingerprint, "train_rows": int(len(train_df))}
            races_out.extend(scored)

        probability_scores = add_probabilities(races_out)
        races_out.sort(key=lambda r: (r["year"], r["round"]), reverse=True)
        logger.info("walk-forward backtest: %d units (%d refitted), %d races", len(units_out), refits, len(races_out))
        return {
            "races": races_out,
            "computed_at": datetime.utcnow().isoformat(),
            "seasons_tested": sorted({int(r["year"]) for r in races_out}),
            "method": {
                "earlier_seasons": "one model per season, trained on the seasons before it",
                "latest_season": latest_year,
                "latest_season_method": "one model per round, trained on everything before that round",
            },
            "probability_scores": probability_scores,
            "hit_rates": hit_rates(races_out),
            "method_version": self.WALK_FORWARD_VERSION,
            "units": units_out,
            "refits": refits,
            # Invalidation key: a walk-forward result is stale once new race results
            # are ingested, not when the live model retrains, so this is keyed to the
            # training data shape rather than self._meta["trained_at"].
            "data_fingerprint": self.data_fingerprint(raw),
        }

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def available_circuits(self) -> List[str]:
        if self._df is None or self._df.empty:
            return []
        return sorted(self._df["circuit_name"].dropna().unique().tolist())

    def training_status(self) -> Dict[str, Any]:
        years = self._meta.get("years", [])
        sprint_rows = 0
        if self._df is not None and "sprint_position" in self._df.columns:
            sprint_rows = int(self._df["sprint_position"].notna().sum())
        return {
            "trained":             bool(self._trained),
            "training":            self._train_lock.locked(),
            "race_model_ready":    bool(self._race_model is not None),
            "quali_model_ready":   bool(self._quali_model is not None),
            "sprint_model_ready":  bool(self._sprint_model is not None),
            "grid_data_available": bool(self._grid_available),
            "training_rows":       int(len(self._df)) if self._df is not None else 0,
            "sprint_training_rows": sprint_rows,
            "circuits":            int(len(self.available_circuits())),
            "years":               [int(y) for y in years],
            "trained_at":          str(self._meta.get("trained_at") or ""),
            "decay_factor":        float(self._meta.get("decay_factor") or TIME_DECAY),
            "grid_coverage":       str(self._meta.get("grid_coverage") or "0%"),
        }
