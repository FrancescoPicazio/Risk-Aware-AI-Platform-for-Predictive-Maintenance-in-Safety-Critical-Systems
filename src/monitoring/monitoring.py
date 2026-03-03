"""
Monitoring & Drift Detection Module
=====================================
Listens on two MQTT topics:

* ``cmapss/scheduler``  – type=MONITORING triggers the daily report
* ``cmapss/inference``  – type=RUL_PREDICTION accumulates live predictions

On each monitoring trigger it:
1. Computes a basic performance summary (mean RUL, std, prediction count)
2. Detects prediction drift vs. a rolling baseline (simple z-score)
3. Writes the report to data/results/monitoring_report.json
4. Logs a human-readable summary
"""

import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import List

import numpy as np

from configs import config
from src.common.components import PipelineComponent

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
RESULTS_DIR: str = config.DATA["RESULTS"]
BASELINE_WINDOW: int = 100    # number of predictions used as rolling baseline
DRIFT_Z_THRESHOLD: float = 3.0  # z-score above which drift is flagged


class Monitoring(PipelineComponent):
    """
    Collects live RUL predictions and produces periodic monitoring reports.
    """

    def __init__(self):
        super().__init__(
            "Monitoring",
            [
                config.MQTT["TOPICS"]["SCHEDULER"],
                config.MQTT["TOPICS"]["INFERENCE"],
            ]
        )
        # Rolling buffer of recent rul_mean values for drift detection
        self._prediction_buffer: deque = deque(maxlen=BASELINE_WINDOW * 2)
        self._report_requested: bool = False
        Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)

    def setup(self) -> None:
        super().setup()
        self.logger.info(f"{self.name}: setup complete")

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------
    def on_message_received(self, payload: dict) -> None:
        msg_type = payload.get("type")

        if msg_type == "MONITORING":
            self.logger.info(f"{self.name}: monitoring report requested")
            self._report_requested = True

        elif msg_type == "RUL_PREDICTION":
            rul_mean = payload.get("rul_mean")
            if rul_mean is not None:
                self._prediction_buffer.append({
                    "unit_id": payload.get("unit_id"),
                    "rul_mean": float(rul_mean),
                    "rul_std": float(payload.get("rul_std", 0.0)),
                    "timestamp": payload.get("timestamp", time.time()),
                })

        elif msg_type == "TRAINING_COMPLETE":
            self.logger.info(
                f"{self.name}: new model registered – "
                f"run_id={payload.get('run_id')} RMSE={payload.get('rmse')}"
            )

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------
    def execute(self) -> None:
        if not self._report_requested:
            return
        self._report_requested = False
        self._generate_report()

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------
    def _generate_report(self) -> None:
        buffer: List[dict] = list(self._prediction_buffer)

        if not buffer:
            self.logger.info(f"{self.name}: no predictions available yet – skipping report")
            return

        rul_values = np.array([r["rul_mean"] for r in buffer])

        # Performance summary
        summary = {
            "n_predictions": len(rul_values),
            "rul_mean": float(np.mean(rul_values)),
            "rul_std": float(np.std(rul_values)),
            "rul_min": float(np.min(rul_values)),
            "rul_max": float(np.max(rul_values)),
            "rul_p5": float(np.percentile(rul_values, 5)),
            "rul_p95": float(np.percentile(rul_values, 95)),
        }

        # Drift detection: compare first half vs second half of buffer
        drift_detected = False
        drift_details = {}
        if len(rul_values) >= BASELINE_WINDOW:
            baseline = rul_values[:BASELINE_WINDOW]
            recent = rul_values[BASELINE_WINDOW:]
            baseline_mean = float(np.mean(baseline))
            baseline_std = float(np.std(baseline)) or 1.0
            recent_mean = float(np.mean(recent))
            z_score = abs(recent_mean - baseline_mean) / baseline_std
            drift_detected = z_score > DRIFT_Z_THRESHOLD
            drift_details = {
                "baseline_mean": round(baseline_mean, 3),
                "recent_mean": round(recent_mean, 3),
                "z_score": round(z_score, 3),
                "threshold": DRIFT_Z_THRESHOLD,
                "drift_detected": drift_detected,
            }

        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": summary,
            "drift": drift_details,
        }

        # Write report
        report_path = Path(RESULTS_DIR) / "monitoring_report.json"
        existing = []
        if report_path.exists():
            try:
                with open(report_path) as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
            except Exception:
                existing = []
        existing.append(report)
        with open(report_path, "w") as f:
            json.dump(existing, f, indent=2)

        # Human-readable log
        self.logger.info(
            f"{self.name}: report generated – "
            f"n={summary['n_predictions']} "
            f"RUL_mean={summary['rul_mean']:.1f} "
            f"drift={'⚠️ YES' if drift_detected else 'OK'}"
        )
        if drift_detected:
            self.logger.warning(
                f"{self.name}: DRIFT DETECTED – "
                f"z-score={drift_details['z_score']:.2f} "
                f"(baseline={drift_details['baseline_mean']:.1f} "
                f"vs recent={drift_details['recent_mean']:.1f})"
            )

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("\n" + "=" * 60)
    print("📈 [MONITORING & DRIFT DETECTION CONTAINER ONLINE]")
    print("=" * 60 + "\n")

    mon = Monitoring()
    mon.setup()

    try:
        while True:
            mon.execute()
            time.sleep(1.0)
    except KeyboardInterrupt:
        mon.teardown()
        logging.getLogger(__name__).info("🛑 Monitoring stopped")
