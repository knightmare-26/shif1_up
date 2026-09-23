"""
F1 Race & Qualifying Prediction Service
- Qualifying: XGBoost predicts grid position from driver/team circuit history
- Race:       LightGBM predicts finishing position using predicted grid + form features
- Training:   Exponential time decay (1.5^(year - oldest)) — recent seasons weighted higher
- Persistence: Models saved to data/models/ and reloaded on startup (no cold retrain)
"""

import json
import logging
import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Exponential decay factor — 2024 gets 1.5^4 ≈ 5× the weight of 2020
TIME_DECAY = 1.5

# Features used when grid data is available (after re-ingest)
RACE_FEATURES_FULL = [
    "grid", "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate", "driver_teammate_finish_delta",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]

# Fallback when grid is NULL (before re-ingest)
RACE_FEATURES_NO_GRID = [
    "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate", "driver_teammate_finish_delta",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]

QUALI_FEATURES = [
    "driver_rolling_grid", "driver_circuit_grid_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_teammate_grid_delta",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]

# Sprint race features mirror the race model's, but use the sprint grid
# (from sprint qualifying) instead of the main race grid as the input —
# everything else (form, circuit avg, dnf rate) is shared driver/constructor
# state going into that race weekend, not sprint-specific.
SPRINT_FEATURES_FULL = [
    "sprint_grid", "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate", "driver_teammate_finish_delta",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]

SPRINT_FEATURES_NO_GRID = [
    "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate", "driver_teammate_finish_delta",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]


class PredictionService:
    # Everything a training run produces. Fitting happens on a private copy holding these
    # and the result is swapped in all at once, so requests never see half-updated models.
    _FITTED = (
        "_race_model", "_quali_model", "_sprint_model", "_race_features", "_sprint_features",
        "_df", "_driver_map", "_constructor_map", "_le_driver", "_le_constructor", "_le_circuit",
        "_trained", "_grid_available", "_meta",
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
        self._sprint_features: List[str] = SPRINT_FEATURES_NO_GRID
        self._df: Optional[pd.DataFrame] = None
        self._driver_map: Dict[str, str] = {}
        self._constructor_map: Dict[str, str] = {}
        self._le_driver: List[str] = []
        self._le_constructor: List[str] = []
        self._le_circuit: List[str] = []
        self._trained = False
        self._grid_available = False
        self._meta: Dict[str, Any] = {}

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

        # Teammate delta: a rolling average of (this driver's result - their teammate's,
        # same race) isolates driver skill from car performance — a mid-season car upgrade
        # moves both teammates' rolling_finish together but leaves this delta unchanged.
        # Find the teammate via a self-merge on (race_id, constructor_id), excluding self;
        # .mean() over the merge handles the rare case of >2 drivers sharing a constructor
        # in one race (a mid-season swap) rather than double-counting.
        teammates = df[["race_id", "constructor_id", "driver_id", "position", "grid"]].rename(
            columns={"driver_id": "driver_id_team", "position": "position_team", "grid": "grid_team"}
        )
        paired = df[["race_id", "constructor_id", "driver_id"]].merge(
            teammates, on=["race_id", "constructor_id"]
        )
        paired = paired[paired["driver_id"] != paired["driver_id_team"]]
        teammate_avg = paired.groupby(["race_id", "driver_id"], as_index=False).agg(
            teammate_position=("position_team", "mean"), teammate_grid=("grid_team", "mean")
        )
        df = df.merge(teammate_avg, on=["race_id", "driver_id"], how="left")

        df["driver_teammate_finish_delta"] = df.groupby("driver_id").apply(
            lambda g: roll(g["position"] - g["teammate_position"])
        ).reset_index(level=0, drop=True)
        df["driver_teammate_grid_delta"] = df.groupby("driver_id").apply(
            lambda g: roll(g["grid"] - g["teammate_grid"])
        ).reset_index(level=0, drop=True)
        df = df.drop(columns=["teammate_position", "teammate_grid"])

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
        # No measurable delta yet (a driver's first races, or no teammate that race) — neutral, not missing.
        df["driver_teammate_finish_delta"] = df["driver_teammate_finish_delta"].fillna(0.0)
        df["driver_teammate_grid_delta"]   = df["driver_teammate_grid_delta"].fillna(0.0)

        return df

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

    def _new_race_model(self, lgb):
        return lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=6,
            num_leaves=31, min_child_samples=5, random_state=42, verbose=-1,
        )

    def _new_quali_model(self, xgb):
        return xgb.XGBRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=6,
            random_state=42, verbosity=0,
        )

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    async def train(self, duckdb_service) -> Dict[str, Any]:
        """Train (or retrain) the models. Serialised: a second caller waits for the first."""
        async with self._train_lock:
            return await self._train_locked(duckdb_service)

    async def _train_locked(self, duckdb_service) -> Dict[str, Any]:
        try:
            import xgboost as xgb
            import lightgbm as lgb
        except ImportError as exc:
            return {"success": False, "error": f"ML packages missing: {exc}. Run: pip install xgboost lightgbm"}

        try:
            raw = await self._load_raw(duckdb_service)
            if raw.empty or len(raw) < 20:
                return {"success": False, "error": f"Insufficient data ({len(raw)} rows). Run ingest first."}

            # Fitting is CPU-bound and used to run right on the event loop, stalling every
            # request (including /health) for its whole duration. Run it in a worker thread,
            # on a private copy of the state, and swap the result in when it's done.
            scratch = self._scratch_copy()
            result = await asyncio.to_thread(scratch._fit, raw, xgb, lgb)
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

    def _fit(self, raw: pd.DataFrame, xgb, lgb) -> Dict[str, Any]:
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

        self._df = df

        result: Dict[str, Any] = {
            "rows": len(df),
            "years": years_in_data,
            "decay_factor": TIME_DECAY,
        }

        # ---- Race model (LightGBM) ----
        grid_coverage = df["grid"].notna().mean()
        self._grid_available  = bool(grid_coverage > 0.5)
        self._race_features   = RACE_FEATURES_FULL if self._grid_available else RACE_FEATURES_NO_GRID
        result["grid_coverage"] = f"{grid_coverage:.0%}"

        race_df = df.dropna(subset=self._race_features + ["position"])
        if len(race_df) >= 20:
            X_r = race_df[self._race_features].astype(float)
            y_r = race_df["position"].astype(float).values
            w_r = self._time_weights(race_df).astype(np.float64)
            self._race_model = self._new_race_model(lgb)
            self._race_model.fit(X_r, y_r, sample_weight=w_r)
            result["race_training_rows"] = len(race_df)
        else:
            result["race_model"] = "skipped — not enough complete rows"

        # ---- Qualifying model (XGBoost) ----
        quali_df = df.dropna(subset=QUALI_FEATURES + ["grid"])
        if len(quali_df) >= 20:
            X_q = quali_df[QUALI_FEATURES].astype(float)
            y_q = quali_df["grid"].astype(float).values
            w_q = self._time_weights(quali_df).astype(np.float64)
            self._quali_model = self._new_quali_model(xgb)
            self._quali_model.fit(X_q, y_q, sample_weight=w_q)
            result["quali_training_rows"] = len(quali_df)
        else:
            result["quali_model"] = "skipped — grid column is NULL. Re-ingest data to populate grid positions."

        # ---- Sprint model (LightGBM) ----
        # Sprints are much rarer than full races (roughly half a dozen a
        # season, only since 2021), so this trains on far fewer rows than
        # the race model — expect lower confidence until more are ingested.
        sprint_grid_coverage = df["sprint_grid"].notna().mean() if df["sprint_position"].notna().any() else 0.0
        sprint_grid_available = bool(sprint_grid_coverage > 0.5)
        self._sprint_features = SPRINT_FEATURES_FULL if sprint_grid_available else SPRINT_FEATURES_NO_GRID
        result["sprint_grid_coverage"] = f"{sprint_grid_coverage:.0%}"

        sprint_df = df.dropna(subset=self._sprint_features + ["sprint_position"])
        if len(sprint_df) >= 20:
            X_s = sprint_df[self._sprint_features].astype(float)
            y_s = sprint_df["sprint_position"].astype(float).values
            w_s = self._time_weights(sprint_df).astype(np.float64)
            self._sprint_model = self._new_race_model(lgb)
            self._sprint_model.fit(X_s, y_s, sample_weight=w_s)
            result["sprint_training_rows"] = len(sprint_df)
        else:
            result["sprint_model"] = f"skipped — only {len(sprint_df)} historical sprint rows (need 20+). Ingest more sprint weekends."

        self._trained = True
        self._meta = {
            "trained_at": datetime.utcnow().isoformat(),
            "rows": len(df),
            "years": years_in_data,
            "decay_factor": TIME_DECAY,
            "grid_coverage": result["grid_coverage"],
            "race_model_ready": self._race_model is not None,
            "quali_model_ready": self._quali_model is not None,
            "sprint_model_ready": self._sprint_model is not None,
        }

        self._save_to_disk()
        return result

    # ------------------------------------------------------------------
    # Feature rows for a future race at a given circuit
    # ------------------------------------------------------------------

    def _build_prediction_rows(self, circuit_name: str) -> pd.DataFrame:
        df = self._df
        # Only predict for drivers who raced in the most recent season
        most_recent_year = int(df["year"].max())
        recent_drivers = df[df["year"] == most_recent_year]["driver_id"].unique()
        df_recent = df[df["driver_id"].isin(recent_drivers)]
        latest = df_recent.sort_values(["year", "round"]).groupby("driver_id").last().reset_index()

        circuit_round_series = df[df["circuit_name"] == circuit_name]["round"]
        circuit_round = int(circuit_round_series.mode().iloc[0]) if not circuit_round_series.empty else 1

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
                "driver_teammate_finish_delta": float(r.get("driver_teammate_finish_delta") or 0.0),
                "driver_teammate_grid_delta":   float(r.get("driver_teammate_grid_delta") or 0.0),
                "round": circuit_round,
            })

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Public predict API
    # ------------------------------------------------------------------

    async def _ensure_trained(self, duckdb_service):
        # Also retrain if df is missing (e.g. loaded from disk but df not persisted)
        if self._trained and self._df is not None:
            return
        # Single-flight: concurrent callers (three predictions in parallel, or the startup
        # warm-up) wait here for the one training instead of each starting their own.
        async with self._train_lock:
            if self._trained and self._df is not None:
                return  # someone finished while we waited
            if not self.load_from_disk() or self._df is None:
                await self._train_locked(duckdb_service)

    async def predict_qualifying(self, circuit_name: str, duckdb_service) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._quali_model is None:
            return {
                "success": False,
                "error": "Qualifying model unavailable — grid data is missing. Re-ingest 2020–2024 data to populate grid positions.",
                "predictions": [],
            }

        trained_at = self._meta.get("trained_at")
        cached = await duckdb_service.get_prediction_cache(circuit_name, "qualifying")
        if cached and cached.get("model_trained_at") == trained_at:
            return cached["result"]

        feat  = self._build_prediction_rows(circuit_name)
        feat  = self._encode(feat)
        preds = self._quali_model.predict(feat[QUALI_FEATURES].fillna(10))
        feat["predicted_grid"] = preds
        feat  = feat.sort_values("predicted_grid").reset_index(drop=True)

        output = []
        for rank, row in feat.iterrows():
            output.append({
                "predicted_rank":   rank + 1,
                "driver_id":        row["driver_id"],
                "driver_name":      self._driver_map.get(row["driver_id"], row["driver_id"]),
                "constructor_id":   row["constructor_id"],
                "constructor_name": self._constructor_map.get(row["constructor_id"], row["constructor_id"]),
                "predicted_grid":   round(float(row["predicted_grid"]), 2),
                "circuit_avg_grid": round(float(row["driver_circuit_grid_avg"]), 2) if pd.notna(row.get("driver_circuit_grid_avg")) else None,
                "rolling_avg_grid": round(float(row["driver_rolling_grid"]), 2)     if pd.notna(row.get("driver_rolling_grid"))      else None,
            })

        result = {
            "success": True,
            "circuit": circuit_name,
            "model": "XGBoost",
            "grid_data_available": self._grid_available,
            "predictions": output,
        }
        await duckdb_service.set_prediction_cache(circuit_name, "qualifying", trained_at, result)
        return result

    async def predict_race(self, circuit_name: str, duckdb_service) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._race_model is None:
            return {"success": False, "error": "Race model unavailable.", "predictions": []}

        trained_at = self._meta.get("trained_at")
        cached = await duckdb_service.get_prediction_cache(circuit_name, "race")
        if cached and cached.get("model_trained_at") == trained_at:
            return cached["result"]

        feat = self._build_prediction_rows(circuit_name)

        # Pipe qualifying predictions in as the grid input
        if self._quali_model is not None:
            feat_q      = self._encode(feat.copy())
            quali_preds = self._quali_model.predict(feat_q[QUALI_FEATURES].fillna(10))
            feat["grid"] = quali_preds

        feat  = self._encode(feat)
        preds = self._race_model.predict(feat[self._race_features].fillna(10))
        feat["predicted_position"] = preds
        feat  = feat.sort_values("predicted_position").reset_index(drop=True)

        output = []
        for rank, row in feat.iterrows():
            output.append({
                "predicted_rank":     rank + 1,
                "driver_id":          row["driver_id"],
                "driver_name":        self._driver_map.get(row["driver_id"], row["driver_id"]),
                "constructor_id":     row["constructor_id"],
                "constructor_name":   self._constructor_map.get(row["constructor_id"], row["constructor_id"]),
                "predicted_position": round(float(row["predicted_position"]), 2),
                "circuit_avg_finish": round(float(row["driver_circuit_avg"]), 2)      if pd.notna(row.get("driver_circuit_avg"))      else None,
                "rolling_avg_finish": round(float(row["driver_rolling_finish"]), 2)   if pd.notna(row.get("driver_rolling_finish"))   else None,
                "predicted_grid":     round(float(row["grid"]), 2),
            })

        result = {
            "success": True,
            "circuit": circuit_name,
            "model": "LightGBM",
            "grid_data_available": self._grid_available,
            "predictions": output,
        }
        await duckdb_service.set_prediction_cache(circuit_name, "race", trained_at, result)
        return result

    async def predict_sprint(self, circuit_name: str, duckdb_service) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._sprint_model is None:
            return {
                "success": False,
                "error": "Sprint model unavailable — not enough historical sprint results ingested yet.",
                "predictions": [],
            }

        trained_at = self._meta.get("trained_at")
        cached = await duckdb_service.get_prediction_cache(circuit_name, "sprint")
        if cached and cached.get("model_trained_at") == trained_at:
            return cached["result"]

        feat = self._build_prediction_rows(circuit_name)

        # No separate sprint-qualifying model (too little data to train one
        # reliably) — the main qualifying model's prediction is used as a
        # proxy for sprint grid, since both measure one-lap pace.
        if self._quali_model is not None:
            feat_q      = self._encode(feat.copy())
            quali_preds = self._quali_model.predict(feat_q[QUALI_FEATURES].fillna(10))
            feat["sprint_grid"] = quali_preds
        else:
            feat["sprint_grid"] = feat.get("grid", 10)

        feat  = self._encode(feat)
        preds = self._sprint_model.predict(feat[self._sprint_features].fillna(10))
        feat["predicted_position"] = preds
        feat  = feat.sort_values("predicted_position").reset_index(drop=True)

        output = []
        for rank, row in feat.iterrows():
            output.append({
                "predicted_rank":     rank + 1,
                "driver_id":          row["driver_id"],
                "driver_name":        self._driver_map.get(row["driver_id"], row["driver_id"]),
                "constructor_id":     row["constructor_id"],
                "constructor_name":   self._constructor_map.get(row["constructor_id"], row["constructor_id"]),
                "predicted_position": round(float(row["predicted_position"]), 2),
                "circuit_avg_finish": round(float(row["driver_circuit_avg"]), 2)      if pd.notna(row.get("driver_circuit_avg"))      else None,
                "rolling_avg_finish": round(float(row["driver_rolling_finish"]), 2)   if pd.notna(row.get("driver_rolling_finish"))   else None,
                "predicted_grid":     round(float(row["sprint_grid"]), 2),
            })

        result = {
            "success": True,
            "circuit": circuit_name,
            "model": "LightGBM (sprint)",
            "grid_data_available": self._grid_available,
            "predictions": output,
        }
        await duckdb_service.set_prediction_cache(circuit_name, "sprint", trained_at, result)
        return result

    # ------------------------------------------------------------------
    # Backtest: predicted vs actual for real past races
    # ------------------------------------------------------------------

    def _score_group(self, group: pd.DataFrame, quali_model, race_model, race_features: List[str]) -> Optional[Dict[str, Any]]:
        """Score one race's rows against a given model pair. Used by both backtest()
        (the live model) and walk_forward_backtest() (a season-scoped scratch model) —
        takes the models as arguments rather than reading self._quali_model/self._race_model
        so the two callers can pass different ones."""
        drivers: Dict[str, Dict[str, Any]] = {}

        if quali_model is not None:
            qdf = group.dropna(subset=QUALI_FEATURES + ["grid"])
            if not qdf.empty:
                preds = quali_model.predict(qdf[QUALI_FEATURES].fillna(10))
                for (_, row), pred in zip(qdf.iterrows(), preds):
                    d = drivers.setdefault(row["driver_id"], {
                        "driver_id": row["driver_id"],
                        "driver_name": self._driver_map.get(row["driver_id"], row["driver_id"]),
                    })
                    d["predicted_grid"] = round(float(pred), 2)
                    d["actual_grid"] = int(row["grid"]) if pd.notna(row["grid"]) else None

        if race_model is not None:
            rdf = group.dropna(subset=race_features + ["position"])
            if not rdf.empty:
                preds = race_model.predict(rdf[race_features].fillna(10))
                for (_, row), pred in zip(rdf.iterrows(), preds):
                    d = drivers.setdefault(row["driver_id"], {
                        "driver_id": row["driver_id"],
                        "driver_name": self._driver_map.get(row["driver_id"], row["driver_id"]),
                    })
                    d["predicted_position"] = round(float(pred), 2)
                    d["actual_position"] = int(row["position"]) if pd.notna(row["position"]) else None

        if not drivers:
            return None

        driver_rows = sorted(drivers.values(), key=lambda d: d.get("actual_position") or 99)

        quali_errs = [abs(d["predicted_grid"] - d["actual_grid"]) for d in driver_rows
                      if d.get("predicted_grid") is not None and d.get("actual_grid") is not None]
        race_errs = [abs(d["predicted_position"] - d["actual_position"]) for d in driver_rows
                     if d.get("predicted_position") is not None and d.get("actual_position") is not None]

        return {
            "year": int(group["year"].iloc[0]),
            "round": int(group["round"].iloc[0]),
            "race_id": group["race_id"].iloc[0],
            "race_name": group["race_name"].iloc[0],
            "circuit_name": group["circuit_name"].iloc[0],
            "quali_mae": round(sum(quali_errs) / len(quali_errs), 2) if quali_errs else None,
            "race_mae": round(sum(race_errs) / len(race_errs), 2) if race_errs else None,
            "drivers": driver_rows,
        }

    def _score_races(self, df: pd.DataFrame, quali_model, race_model, race_features: List[str]) -> List[Dict[str, Any]]:
        races_out = []
        for _, group in df.groupby(["year", "round", "race_id"], sort=False):
            race = self._score_group(group, quali_model, race_model, race_features)
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

        races_out = self._score_races(df, self._quali_model, self._race_model, self._race_features)
        races_out.sort(key=lambda r: (r["year"], r["round"]), reverse=True)
        return {"races": races_out}

    # ------------------------------------------------------------------
    # Walk-forward backtest: a model trained only on seasons before Y,
    # scored against Y itself — an honest holdout, unlike backtest() above
    # which scores the live model against history it was fit on.
    # ------------------------------------------------------------------

    async def walk_forward_backtest(self, duckdb_service, years_back: int = 3) -> Dict[str, Any]:
        """Retrains once per season boundary (not once per race — that would mean
        60-80 full refits for a 3-year window at ~10s each) and scores each season
        against a model that has never seen that season's results. Expensive
        (3-4x a normal fit); callers should run this in the background and cache
        the result, not call it per-request."""
        raw = await self._load_raw(duckdb_service)
        if raw.empty or len(raw) < 20:
            return {"races": [], "error": f"Insufficient data ({len(raw)} rows)"}

        try:
            import xgboost as xgb
            import lightgbm as lgb
        except ImportError as exc:
            return {"races": [], "error": f"ML packages missing: {exc}"}

        return await asyncio.to_thread(self._walk_forward_fit, raw, xgb, lgb, years_back)

    def _walk_forward_fit(self, raw: pd.DataFrame, xgb, lgb, years_back: int) -> Dict[str, Any]:
        raw_race = raw[raw["session_type"] == "race"].copy()
        if raw_race.empty:
            return {"races": []}

        # Feature engineering runs over the whole history at once — safe because every
        # rolling/expanding feature already uses .shift(1), so a row's features only ever
        # reflect races strictly before it regardless of what else is in the frame. What
        # actually gets walked forward is which rows each season's model is FIT on, below.
        df = self._engineer(raw_race)
        le_driver      = sorted(df["driver_id"].fillna("unknown").unique().tolist())
        le_constructor = sorted(df["constructor_id"].fillna("unknown").unique().tolist())
        le_circuit     = sorted(df["circuit_name"].fillna("unknown").unique().tolist())
        df["driver_enc"]      = self._label_encode(df["driver_id"].fillna("unknown"), le_driver)
        df["constructor_enc"] = self._label_encode(df["constructor_id"].fillna("unknown"), le_constructor)
        df["circuit_enc"]     = self._label_encode(df["circuit_name"].fillna("unknown"), le_circuit)

        all_years = sorted(df["year"].unique().tolist())
        if len(all_years) < 2:
            return {"races": []}

        current_year = datetime.utcnow().year
        test_years = [y for y in all_years if y > all_years[0] and y >= current_year - years_back]

        grid_available = bool(df["grid"].notna().mean() > 0.5)
        race_features = RACE_FEATURES_FULL if grid_available else RACE_FEATURES_NO_GRID

        races_out: List[Dict[str, Any]] = []
        seasons_tested: List[int] = []
        for test_year in test_years:
            train_df = df[df["year"] < test_year]
            test_df = df[df["year"] == test_year]
            if test_df.empty:
                continue

            race_model = None
            race_train = train_df.dropna(subset=race_features + ["position"])
            if len(race_train) >= 20:
                race_model = self._new_race_model(lgb)
                race_model.fit(
                    race_train[race_features].astype(float),
                    race_train["position"].astype(float).values,
                    sample_weight=self._time_weights(race_train),
                )

            quali_model = None
            quali_train = train_df.dropna(subset=QUALI_FEATURES + ["grid"])
            if len(quali_train) >= 20:
                quali_model = self._new_quali_model(xgb)
                quali_model.fit(
                    quali_train[QUALI_FEATURES].astype(float),
                    quali_train["grid"].astype(float).values,
                    sample_weight=self._time_weights(quali_train),
                )

            if race_model is None and quali_model is None:
                continue

            seasons_tested.append(int(test_year))
            races_out.extend(self._score_races(test_df, quali_model, race_model, race_features))

        races_out.sort(key=lambda r: (r["year"], r["round"]), reverse=True)
        return {
            "races": races_out,
            "computed_at": datetime.utcnow().isoformat(),
            "seasons_tested": seasons_tested,
            # Invalidation key: a walk-forward result is stale once new race results
            # are ingested, not when the live model retrains, so this is keyed to the
            # training data shape rather than self._meta["trained_at"].
            "data_fingerprint": f"{len(raw_race)}:{max(all_years)}",
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
