"""
F1 Race & Qualifying Prediction Service
- Qualifying: XGBoost predicts grid position from driver/team circuit history
- Race:       LightGBM predicts finishing position using predicted grid + form features
- Training:   Exponential time decay (1.5^(year - oldest)) — recent seasons weighted higher
- Persistence: Models saved to data/models/ and reloaded on startup (no cold retrain)
"""

import json
import logging
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
    "driver_dnf_rate", "driver_enc", "constructor_enc", "circuit_enc", "round",
]

# Fallback when grid is NULL (before re-ingest)
RACE_FEATURES_NO_GRID = [
    "driver_rolling_finish", "driver_circuit_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_dnf_rate", "driver_enc", "constructor_enc", "circuit_enc", "round",
]

QUALI_FEATURES = [
    "driver_rolling_grid", "driver_circuit_grid_avg",
    "constructor_rolling_finish", "constructor_circuit_avg",
    "driver_enc", "constructor_enc", "circuit_enc", "round",
]


class PredictionService:
    def __init__(self, model_dir: str = "data/models"):
        self._model_dir = model_dir
        self._race_model = None
        self._quali_model = None
        self._race_features: List[str] = RACE_FEATURES_NO_GRID
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

            joblib.dump(
                {
                    "le_driver": self._le_driver,
                    "le_constructor": self._le_constructor,
                    "le_circuit": self._le_circuit,
                    "driver_map": self._driver_map,
                    "constructor_map": self._constructor_map,
                    "race_features": self._race_features,
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
            self._grid_available  = enc.get("grid_available", False)

            if os.path.exists(race_path):
                self._race_model = joblib.load(race_path)

            quali_path = os.path.join(self._model_dir, "quali_model.pkl")
            if os.path.exists(quali_path):
                self._quali_model = joblib.load(quali_path)

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
                rr.position, rr.grid, rr.points, rr.status,
                r.circuit_name, r.year, r.round,
                d.full_name  AS driver_name,
                c.constructor_name
            FROM race_results rr
            JOIN races r             ON rr.race_id      = r.race_id
            JOIN drivers d           ON rr.driver_id    = d.driver_id
            LEFT JOIN constructors c ON rr.constructor_id = c.constructor_id
            WHERE rr.position IS NOT NULL
            ORDER BY r.year, r.round
        """)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

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
    # Training
    # ------------------------------------------------------------------

    async def train(self, duckdb_service) -> Dict[str, Any]:
        try:
            import xgboost as xgb
            import lightgbm as lgb
        except ImportError as exc:
            return {"success": False, "error": f"ML packages missing: {exc}. Run: pip install xgboost lightgbm"}

        try:
            raw = await self._load_raw(duckdb_service)
            if raw.empty or len(raw) < 20:
                return {"success": False, "error": f"Insufficient data ({len(raw)} rows). Run ingest first."}

            years_in_data = sorted(raw["year"].unique().tolist())
            self._driver_map      = raw.drop_duplicates("driver_id").set_index("driver_id")["driver_name"].to_dict()
            self._constructor_map = (raw.dropna(subset=["constructor_id"])
                                        .drop_duplicates("constructor_id")
                                        .set_index("constructor_id")["constructor_name"].to_dict())

            df = self._engineer(raw)
            self._le_driver      = sorted(df["driver_id"].fillna("unknown").unique().tolist())
            self._le_constructor = sorted(df["constructor_id"].fillna("unknown").unique().tolist())
            self._le_circuit     = sorted(df["circuit_name"].fillna("unknown").unique().tolist())
            df = self._encode(df)
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
                self._race_model = lgb.LGBMRegressor(
                    n_estimators=300, learning_rate=0.05, max_depth=6,
                    num_leaves=31, min_child_samples=5, random_state=42, verbose=-1,
                )
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
                self._quali_model = xgb.XGBRegressor(
                    n_estimators=300, learning_rate=0.05, max_depth=6,
                    random_state=42, verbosity=0,
                )
                self._quali_model.fit(X_q, y_q, sample_weight=w_q)
                result["quali_training_rows"] = len(quali_df)
            else:
                result["quali_model"] = "skipped — grid column is NULL. Re-ingest data to populate grid positions."

            self._trained = True
            self._meta = {
                "trained_at": datetime.utcnow().isoformat(),
                "rows": len(df),
                "years": years_in_data,
                "decay_factor": TIME_DECAY,
                "grid_coverage": result["grid_coverage"],
                "race_model_ready": self._race_model is not None,
                "quali_model_ready": self._quali_model is not None,
            }

            self._save_to_disk()
            logger.info("Prediction models trained: %s", result)
            return {"success": True, **result}

        except Exception as exc:
            logger.error("Training failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

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
                "round": circuit_round,
            })

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Public predict API
    # ------------------------------------------------------------------

    async def _ensure_trained(self, duckdb_service):
        # Also retrain if df is missing (e.g. loaded from disk but df not persisted)
        if not self._trained or self._df is None:
            if not self.load_from_disk() or self._df is None:
                await self.train(duckdb_service)

    async def predict_qualifying(self, circuit_name: str, duckdb_service) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._quali_model is None:
            return {
                "success": False,
                "error": "Qualifying model unavailable — grid data is missing. Re-ingest 2020–2024 data to populate grid positions.",
                "predictions": [],
            }

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

        return {
            "success": True,
            "circuit": circuit_name,
            "model": "XGBoost",
            "grid_data_available": self._grid_available,
            "predictions": output,
        }

    async def predict_race(self, circuit_name: str, duckdb_service) -> Dict[str, Any]:
        await self._ensure_trained(duckdb_service)

        if self._race_model is None:
            return {"success": False, "error": "Race model unavailable.", "predictions": []}

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

        return {
            "success": True,
            "circuit": circuit_name,
            "model": "LightGBM",
            "grid_data_available": self._grid_available,
            "predictions": output,
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
        return {
            "trained":             bool(self._trained),
            "race_model_ready":    bool(self._race_model is not None),
            "quali_model_ready":   bool(self._quali_model is not None),
            "grid_data_available": bool(self._grid_available),
            "training_rows":       int(len(self._df)) if self._df is not None else 0,
            "circuits":            int(len(self.available_circuits())),
            "years":               [int(y) for y in years],
            "trained_at":          str(self._meta.get("trained_at") or ""),
            "decay_factor":        float(self._meta.get("decay_factor") or TIME_DECAY),
            "grid_coverage":       str(self._meta.get("grid_coverage") or "0%"),
        }
