"""
Training Pipeline
=================
Dual-mode component:

MODE 1 – Scheduled retraining  (trigger: SCHEDULER topic, type=TRAINING)
    * Scans data/processed for all Parquet files
    * If enough data is available (>= MIN_TRAINING_ROWS) trains the LSTM
    * Saves the model to data/model_artifacts
    * Writes metrics to data/results/model_metrics.json

MODE 2 – Streaming inference  (trigger: TRAINING topic, type=FEATURES_READY)
    * Loads the best model from data/model_artifacts
    * Reads the processed Parquet for the notified unit
    * Runs MC-Dropout prediction
    * Publishes the prediction to cmapss/inference topic

Bootstrap behaviour
-------------------
If no model exists when FEATURES_READY arrives the pipeline enters a
collection phase and waits until enough data is accumulated before training.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from configs import config
from src.common.components import PipelineComponent
from src.model.model_engine import ModelEngine, MIN_TRAINING_ROWS


class TrainingPipeline(PipelineComponent):
    """
    Listens on two MQTT topics:
    * ``cmapss/scheduler``  – for scheduled retraining triggers
    * ``cmapss/training``   – for FEATURES_READY inference triggers from FE
    """

    def __init__(self):
        super().__init__(
            "TrainingPipeline",
            [
                config.MQTT["TOPICS"]["SCHEDULER"],
                config.MQTT["TOPICS"]["TRAINING"],
            ]
        )
        self._engine = ModelEngine(
            artifacts_dir=config.DATA["MODEL_ARTIFACTS"],
            results_dir=config.DATA["RESULTS"],
        )
        self._retrain_requested: bool = False
        self._inference_queue: list = []   # list of unit_ids to run inference on

    def setup(self) -> None:
        super().setup()
        self.logger.info(f"{self.name}: setup complete")

    # ------------------------------------------------------------------
    # MQTT incoming messages
    # ------------------------------------------------------------------
    def on_message_received(self, payload: dict) -> None:
        msg_type = payload.get("type")

        if msg_type == "TRAINING":
            # Scheduler triggered a scheduled retraining cycle
            self.logger.info(f"{self.name}: scheduled retraining requested")
            self._retrain_requested = True

        elif msg_type == "FEATURES_READY":
            # Feature Engineering published new processed data
            unit_id = payload.get("unit_id")
            self.logger.info(
                f"{self.name}: FEATURES_READY for unit {unit_id} "
                f"({payload.get('n_rows')} rows)"
            )
            self._inference_queue.append(unit_id)

        else:
            # Ignore other scheduler signals (STREAMING, MONITORING)
            pass

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------
    def execute(self) -> None:
        # --- Mode 1: scheduled retraining ---
        if self._retrain_requested:
            self._retrain_requested = False
            self._run_scheduled_training()

        # --- Mode 2: streaming inference ---
        while self._inference_queue:
            unit_id = self._inference_queue.pop(0)
            self._run_inference(unit_id)

    # ------------------------------------------------------------------
    # Mode 1 – Scheduled training
    # ------------------------------------------------------------------
    def _run_scheduled_training(self) -> None:
        self.logger.info(f"{self.name}: scanning processed data …")
        df = self._load_all_processed()

        if df is None or len(df) < MIN_TRAINING_ROWS:
            n = len(df) if df is not None else 0
            self.logger.info(
                f"{self.name}: not enough data for training "
                f"({n} rows, need >= {MIN_TRAINING_ROWS}). "
                f"Waiting for more data to accumulate."
            )
            return

        self.logger.info(
            f"{self.name}: starting training on {len(df)} rows …"
        )
        try:
            metrics = self._engine.train(df)
            self.logger.info(
                f"{self.name}: training complete – "
                f"RMSE={metrics['rmse']} NASA={metrics['nasa_score']} "
                f"model={metrics['model_path']}"
            )
            # Publish result summary to inference topic
            self.send_message(config.MQTT["TOPICS"]["INFERENCE"], {
                "type": "TRAINING_COMPLETE",
                "run_id": metrics["run_id"],
                "rmse": metrics["rmse"],
                "nasa_score": metrics["nasa_score"],
                "timestamp": time.time(),
            })
        except Exception as exc:
            self.logger.error(f"{self.name}: training failed – {exc}")

    # ------------------------------------------------------------------
    # Mode 2 – Streaming inference
    # ------------------------------------------------------------------
    def _run_inference(self, unit_id: Optional[int]) -> None:
        # Lazily load the best model (only when needed / after retraining)
        if self._engine._model is None:
            loaded = self._engine.load_best()
            if not loaded:
                self.logger.warning(
                    f"{self.name}: no model available yet – "
                    f"collecting data for unit {unit_id}."
                )
                # Trigger a retraining attempt after this inference batch
                self._retrain_requested = True
                return

        # Load processed data for this unit
        df_unit = self._load_unit_processed(unit_id)
        if df_unit is None or len(df_unit) < 2:
            self.logger.warning(
                f"{self.name}: no processed data for unit {unit_id}"
            )
            return

        try:
            result = self._engine.predict(df_unit)
            self.logger.info(
                f"{self.name}: unit {unit_id} – "
                f"RUL={result['rul_mean']:.1f} ± {result['rul_std']:.1f} "
                f"[{result['rul_lower']:.1f}, {result['rul_upper']:.1f}]"
            )
            # Publish prediction to inference topic
            self.send_message(config.MQTT["TOPICS"]["INFERENCE"], {
                "type": "RUL_PREDICTION",
                "unit_id": unit_id,
                "rul_mean": result["rul_mean"],
                "rul_std": result["rul_std"],
                "rul_lower": result["rul_lower"],
                "rul_upper": result["rul_upper"],
                "timestamp": time.time(),
            })
        except Exception as exc:
            self.logger.error(
                f"{self.name}: inference failed for unit {unit_id} – {exc}"
            )

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------
    def _load_all_processed(self) -> Optional[pd.DataFrame]:
        """Load all Parquet files from data/processed recursively."""
        processed_dir = Path(config.DATA["PROCESSED"])
        parquet_files = list(processed_dir.rglob("*.parquet"))
        if not parquet_files:
            return None
        frames = []
        for p in parquet_files:
            try:
                frames.append(pd.read_parquet(p))
            except ImportError as exc:
                self.logger.error(
                    f"{self.name}: Parquet engine missing – "
                    f"install pyarrow: pip install pyarrow>=14.0.0  ({exc})"
                )
                raise
            except Exception as exc:
                self.logger.warning(f"{self.name}: skipping {p} – {exc}")
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    def _load_unit_processed(self, unit_id: Optional[int]) -> Optional[pd.DataFrame]:
        """Load processed Parquet files for a specific unit_id."""
        processed_dir = Path(config.DATA["PROCESSED"])
        parquet_files = list(processed_dir.rglob(f"unit_{unit_id:04d}.parquet"))
        if not parquet_files:
            # Fallback: load all and filter
            df_all = self._load_all_processed()
            if df_all is None:
                return None
            return df_all[df_all["unit_id"] == unit_id].copy()
        frames = []
        for p in parquet_files:
            try:
                frames.append(pd.read_parquet(p))
            except ImportError as exc:
                self.logger.error(
                    f"{self.name}: Parquet engine missing – "
                    f"install pyarrow: pip install pyarrow>=14.0.0  ({exc})"
                )
                raise
            except Exception as exc:
                self.logger.warning(f"{self.name}: skipping {p} – {exc}")
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("\n" + "=" * 60)
    print("🧠 [TRAINING PIPELINE CONTAINER ONLINE]")
    print("=" * 60)
    logging.getLogger(__name__).info(
        f"Model artifacts: {os.getenv('MODEL_OUTPUT_PATH', config.DATA['MODEL_ARTIFACTS'])}"
    )
    print("=" * 60 + "\n")

    training = TrainingPipeline()
    training.setup()

    try:
        while True:
            training.execute()
            time.sleep(0.1)
    except KeyboardInterrupt:
        training.teardown()
        logging.getLogger(__name__).info("🛑 Training Pipeline stopped")
