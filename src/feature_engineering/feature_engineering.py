"""
Feature Engineering Module
===========================
Receives cleaned sensor records from Data Ingestion via MQTT, accumulates
them in a per-unit rolling buffer, computes engineered features and, once a
complete engine run (end-of-file signal or buffer full) is detected, saves
the enriched dataset to ``data/processed/`` and publishes a notification to
the Training Pipeline.

Feature engineering steps
--------------------------
1. Rolling statistics  – mean, std, min, max over a configurable window
2. EWMA smoothing      – exponentially weighted moving average (α = 0.1)
3. Cycle-normalised health index – based on selected high-information sensors
4. Delta features      – cycle-over-cycle first difference for each sensor
"""

import logging
import os
import time
from collections import defaultdict, deque
from typing import Dict, List

import pandas as pd

from configs import config
from src.common.components import PipelineComponent

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
WINDOW_SIZE: int = 30          # rolling window (cycles)
EWMA_ALPHA: float = 0.1        # smoothing factor
BUFFER_FLUSH_SIZE: int = 5000  # flush to disk after this many records per unit
PROCESSED_DIR: str = config.DATA["PROCESSED"]

# High-information sensors selected from CMAPSS literature
# (sensors 2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21)
_HI_SENSORS: List[int] = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21]


def _compute_health_index(row: Dict[str, float]) -> float:
    """
    Approximate health index as the normalised mean of high-information sensor
    values.  Returns a value in [0, 1] where 1 = healthy, 0 = degraded.
    """
    vals = [row.get(f"sensor_{s}", 0.0) for s in _HI_SENSORS]
    if not vals:
        return 0.5
    hi = sum(vals) / len(vals)
    # Clip and normalise to [0, 1] – rough CMAPSS sensor value range is wide,
    # so we use a simple min-max with known global bounds (conservative).
    return max(0.0, min(1.0, hi / 1000.0))


class FeatureEngineering(PipelineComponent):
    """
    Listens on ``cmapss/feature_engineering``, accumulates records per
    engine unit and produces enriched feature vectors.
    """

    def __init__(self):
        super().__init__("FeatureEngineering",
                         [config.MQTT["TOPICS"]["FEATURE_ENGINEERING"]])
        # Buffer: unit_id → deque of cleaned record dicts
        self._buffers: Dict[int, deque] = defaultdict(lambda: deque(maxlen=BUFFER_FLUSH_SIZE * 2))
        # Tracks which units have received new data since last flush
        self._dirty: set = set()
        os.makedirs(PROCESSED_DIR, exist_ok=True)

    def setup(self) -> None:
        super().setup()
        self.logger.info(f"{self.name}: setup complete – window={WINDOW_SIZE} "
                         f"ewma_alpha={EWMA_ALPHA}")

    # ------------------------------------------------------------------
    # MQTT callback
    # ------------------------------------------------------------------
    def on_message_received(self, payload: dict) -> None:
        unit_id = payload.get("unit_id")
        if unit_id is None:
            self.logger.warning(f"{self.name}: payload missing unit_id, skipping")
            return
        self._buffers[unit_id].append(payload)
        self._dirty.add(unit_id)

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------
    def execute(self) -> None:
        """
        For every unit that has received new records, build the feature
        DataFrame, save it to disk and notify the Training Pipeline.
        """
        if not self._dirty:
            return

        units_to_process = list(self._dirty)
        self._dirty.clear()

        for unit_id in units_to_process:
            try:
                records = list(self._buffers[unit_id])
                if len(records) < 2:
                    continue   # not enough data yet

                df = self._build_dataframe(records)
                df = self._engineer_features(df)
                self._save(df, unit_id)
                self._notify_training(unit_id, len(df))
            except Exception as exc:
                self.logger.error(
                    f"{self.name}: error processing unit {unit_id} – {exc}",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_dataframe(self, records: List[dict]) -> pd.DataFrame:
        """Flatten the list of cleaned record dicts into a DataFrame."""
        rows = []
        for rec in records:
            row = {
                "unit_id": rec["unit_id"],
                "cycle": rec["cycle"],
                "timestamp": rec["timestamp"],
                "source_file": rec["source_file"],
            }
            # Unpack operational settings
            for i, val in enumerate(rec.get("operational_settings", []), 1):
                row[f"setting_{i}"] = val
            # Unpack sensors (dict keyed by sensor id)
            for sid, val in rec.get("sensors", {}).items():
                row[f"sensor_{sid}"] = float(val)
            rows.append(row)

        df = pd.DataFrame(rows)
        df = df.sort_values(["unit_id", "cycle"]).reset_index(drop=True)
        return df

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute rolling, EWMA and delta features per unit."""
        sensor_cols = [c for c in df.columns if c.startswith("sensor_")]
        result_frames = []

        for unit_id, group in df.groupby("unit_id"):
            g = group.copy().reset_index(drop=True)

            # Rolling stats
            for col in sensor_cols:
                g[f"{col}_roll_mean"] = (
                    g[col].rolling(WINDOW_SIZE, min_periods=1).mean()
                )
                g[f"{col}_roll_std"] = (
                    g[col].rolling(WINDOW_SIZE, min_periods=1).std().fillna(0.0)
                )
                g[f"{col}_roll_min"] = (
                    g[col].rolling(WINDOW_SIZE, min_periods=1).min()
                )
                g[f"{col}_roll_max"] = (
                    g[col].rolling(WINDOW_SIZE, min_periods=1).max()
                )
                # EWMA smoothing
                g[f"{col}_ewma"] = g[col].ewm(alpha=EWMA_ALPHA, adjust=False).mean()
                # Delta (first difference)
                g[f"{col}_delta"] = g[col].diff().fillna(0.0)

            # Health index (scalar, per cycle)
            sensor_row_dicts = g[sensor_cols].to_dict(orient="records")
            g["health_index"] = [_compute_health_index(r) for r in sensor_row_dicts]

            # Cycle fraction (0=start, 1=approx end) – useful for LSTM
            max_cycle = g["cycle"].max()
            g["cycle_fraction"] = g["cycle"] / max_cycle if max_cycle > 0 else 0.0

            result_frames.append(g)

        return pd.concat(result_frames, ignore_index=True)

    def _save(self, df: pd.DataFrame, unit_id: int) -> None:
        """Persist enriched DataFrame to data/processed as Parquet."""
        source_files = df["source_file"].unique()
        for src in source_files:
            subset = os.path.splitext(src)[0]  # e.g. "train_FD001"
            out_dir = os.path.join(PROCESSED_DIR, subset)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"unit_{unit_id:04d}.parquet")
            part = df[df["source_file"] == src]
            try:
                part.to_parquet(out_path, index=False)
                self.logger.info(
                    f"{self.name}: saved {len(part)} rows → {out_path}"
                )
            except ImportError as exc:
                self.logger.error(
                    f"{self.name}: Parquet engine not available – "
                    f"install pyarrow: pip install pyarrow>=14.0.0 ({exc})"
                )
                raise
            except Exception as exc:
                self.logger.error(
                    f"{self.name}: failed to save {out_path} – {exc}",
                    exc_info=True,
                )
                raise

    def _notify_training(self, unit_id: int, n_rows: int) -> None:
        """Publish a notification to the Training Pipeline topic."""
        notification = {
            "type": "FEATURES_READY",
            "unit_id": unit_id,
            "n_rows": n_rows,
            "processed_dir": PROCESSED_DIR,
            "timestamp": time.time(),
        }
        self.send_message(config.MQTT["TOPICS"]["TRAINING"], notification)

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown – buffered units: "
                         f"{list(self._buffers.keys())}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("\n" + "=" * 60)
    print("⚙️  [FEATURE ENGINEERING CONTAINER ONLINE]")
    print("=" * 60 + "\n")

    fe = FeatureEngineering()
    fe.setup()

    try:
        while True:
            fe.execute()
            time.sleep(0.05)
    except KeyboardInterrupt:
        fe.teardown()
        logging.getLogger(__name__).info("🛑 Feature Engineering stopped")
