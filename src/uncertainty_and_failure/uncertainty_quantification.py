"""
Uncertainty Quantification Module
===================================
Standalone component that performs Monte Carlo Dropout inference on the
trained LSTM model and produces per-engine uncertainty estimates with
calibration analysis.

Behaviour
---------
* Subscribes to ``cmapss/uncertainty`` (topic MQTT).
* For each trigger message (containing ``dataset_id``):
  1. Loads the latest model artifact via ``ModelEngine.load_best()``.
  2. Reads all processed parquet files from ``data/processed/{dataset_id}/``.
  3. Runs **N=100 MC Dropout forward passes** per engine unit.
  4. Computes: ``rul_mean``, ``rul_std``, ``ci_lower_90``, ``ci_upper_90``
     (5th–95th percentile).
  5. Performs calibration analysis (ECE + reliability diagram data) against
     ground-truth RUL values from ``data/raw/RUL_{dataset_id}.txt``.
  6. Persists all results to ``data/results/uncertainty_{dataset_id}.json``.
  7. Publishes the enriched payload to ``cmapss/risk``.

Calibration
-----------
ECE is computed by binning predicted confidence levels (derived from the
MC Dropout distribution) and comparing them to the observed fraction of
actual RUL values within the predicted interval.

The reliability diagram data (bucket_confidence, bucket_accuracy, bucket_count)
is saved as JSON alongside the per-unit predictions.

Usage (standalone)
------------------
    python -m src.uncertainty_and_failure.uncertainty_quantification
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from configs import config
from src.common.components import PipelineComponent
from src.model.model_engine import ModelEngine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MC_SAMPLES: int = 100              # Monte Carlo Dropout forward passes
N_CALIBRATION_BINS: int = 10       # bins for reliability diagram / ECE
RUL_CLIP: int = 125                # piecewise RUL cap (NASA convention)

ARTIFACTS_DIR: str = config.DATA["MODEL_ARTIFACTS"]
PROCESSED_DIR: str = config.DATA["PROCESSED"]
RAW_DIR: str = config.DATA["RAW"]
RESULTS_DIR: str = config.DATA["RESULTS"]

SUBSCRIBE_TOPIC: str = config.MQTT["TOPICS"]["UNCERTAINTY"]
PUBLISH_TOPIC: str = config.MQTT["TOPICS"]["RISK"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------

def compute_ece(
    predicted_intervals: List[Tuple[float, float]],
    actuals: List[float],
    confidence_level: float = 0.90,
    n_bins: int = N_CALIBRATION_BINS,
) -> Tuple[float, List[dict]]:
    """
    Compute Expected Calibration Error (ECE) and reliability diagram data.

    We treat the MC Dropout 90% CI as a *confidence claim*: "we are 90%
    confident the true RUL lies in [ci_lower, ci_upper]".  ECE measures
    how well calibrated these interval claims are across multiple confidence
    levels derived from the MC posterior.

    Strategy
    --------
    For each unit we have ``mc_samples`` draws from the posterior.
    We evaluate coverage at a range of confidence levels α ∈ (0,1) and
    compare claimed coverage α vs. observed fraction of actuals inside
    the [((1-α)/2)*100 th, ((1+α)/2)*100 th] percentile interval.

    Parameters
    ----------
    predicted_intervals : list of (ci_lower_90, ci_upper_90) tuples
        Predicted 90% confidence intervals (5th – 95th percentile).
    actuals             : list of true RUL values (same length).
    confidence_level    : nominal coverage (default 0.90 for 90% CI).
    n_bins              : number of calibration bins.

    Returns
    -------
    ece : float  – Expected Calibration Error
    diagram_data : list of dicts with keys:
        bin_confidence, observed_fraction, count
    """
    if len(predicted_intervals) != len(actuals):
        raise ValueError("predicted_intervals and actuals must have the same length.")

    # Build confidence bins from 1/n_bins to 1 (exclusive of 0)
    bin_edges = np.linspace(1.0 / n_bins, 1.0, n_bins)
    bin_counts = np.zeros(n_bins, dtype=int)
    bin_observed = np.zeros(n_bins, dtype=float)

    for (ci_lower, ci_upper), actual in zip(predicted_intervals, actuals):
        # Estimate empirical coverage at each confidence level using the
        # linear interpolation between ci_lower (5%) and ci_upper (95%).
        # We approximate: for confidence α, the interval is
        #   [ci_lower + (0.05 * (1-α)/0.9 * span), ci_upper - (0.05 * (1-α)/0.9 * span)]
        # but for simplicity we use the following shortcut:
        # the unit "is inside the α CI" iff:
        #   actual >= midpoint - (α/0.9) * half_width AND
        #   actual <= midpoint + (α/0.9) * half_width
        # This keeps the calibration computations self-contained without
        # storing all MC samples.
        mid = (ci_lower + ci_upper) / 2.0
        half_w = (ci_upper - ci_lower) / 2.0   # half-width at 90%

        for b_idx, alpha in enumerate(bin_edges):
            scaled_half = half_w * (alpha / 0.90)
            lo = mid - scaled_half
            hi = mid + scaled_half
            bin_counts[b_idx] += 1
            if lo <= actual <= hi:
                bin_observed[b_idx] += 1

    diagram_data: List[dict] = []
    ece_accum = 0.0
    total = len(actuals)

    for b_idx, alpha in enumerate(bin_edges):
        n = bin_counts[b_idx]
        frac = bin_observed[b_idx] / n if n > 0 else 0.0
        diagram_data.append(
            {
                "bin_confidence": round(float(alpha), 4),
                "observed_fraction": round(frac, 4),
                "count": int(n),
            }
        )
        ece_accum += abs(alpha - frac) * (n / total)

    return float(ece_accum), diagram_data


# ---------------------------------------------------------------------------
# Ground-truth RUL loader (CMAPSS test set)
# ---------------------------------------------------------------------------

def load_ground_truth_rul(dataset_id: str, raw_dir: str) -> Optional[Dict[int, float]]:
    """
    Load the ground-truth final RUL for each unit from
    ``data/raw/RUL_{dataset_id}.txt``.

    Returns a dict mapping unit_index (1-based) → true_rul, or None if the
    file does not exist (e.g. training datasets have no RUL file).
    """
    rul_path = Path(raw_dir) / f"RUL_{dataset_id}.txt"
    if not rul_path.exists():
        return None
    with open(rul_path) as fh:
        values = [float(line.strip()) for line in fh if line.strip()]
    return {idx + 1: v for idx, v in enumerate(values)}


# ---------------------------------------------------------------------------
# PipelineComponent
# ---------------------------------------------------------------------------

class UncertaintyQuantification(PipelineComponent):
    """
    MC Dropout inference component.

    Subscribes to ``cmapss/uncertainty``, runs N=100 forward passes per
    engine unit, computes RUL mean / std / 90% CI, performs calibration
    analysis, persists JSON results and publishes to ``cmapss/risk``.
    """

    def __init__(
        self,
        mc_samples: int = MC_SAMPLES,
        artifacts_dir: str = ARTIFACTS_DIR,
        processed_dir: str = PROCESSED_DIR,
        raw_dir: str = RAW_DIR,
        results_dir: str = RESULTS_DIR,
    ):
        super().__init__(
            name="UncertaintyQuantification",
            mqtt_topic_subscribe_list=[SUBSCRIBE_TOPIC],
        )
        self.mc_samples = int(os.getenv("MC_SAMPLES", mc_samples))
        self.artifacts_dir = artifacts_dir
        self.processed_dir = processed_dir
        self.raw_dir = raw_dir
        self.results_dir = results_dir
        self._queue: List[dict] = []
        self._engine: Optional[ModelEngine] = None

        Path(results_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Connect to MQTT and pre-load the best model artifact."""
        super().setup()
        self._engine = ModelEngine(
            artifacts_dir=self.artifacts_dir,
            results_dir=self.results_dir,
        )
        loaded = self._engine.load_best()
        if loaded:
            self.logger.info(f"{self.name}: model loaded successfully (MC samples={self.mc_samples})")
        else:
            self.logger.warning(
                f"{self.name}: no model artifact found – "
                "inference will fail until a model is trained and load_best() succeeds."
            )

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown complete")

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def on_message_received(self, payload: dict) -> None:
        """
        Accept messages of type ``UQ_REQUEST`` or any message containing
        a ``dataset_id`` field.  Re-trigger a model load if requested.
        """
        msg_type = payload.get("type", "")
        dataset_id = payload.get("dataset_id")

        if not dataset_id:
            self.logger.warning(f"{self.name}: received message without dataset_id – skipped")
            return

        if msg_type == "MODEL_RELOAD" and self._engine:
            self.logger.info(f"{self.name}: reloading model on request…")
            self._engine.load_best()

        self.logger.info(f"{self.name}: queued UQ request for dataset_id={dataset_id}")
        self._queue.append(payload)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def execute(self) -> None:
        """Process all pending UQ requests from the queue."""
        while self._queue:
            item = self._queue.pop(0)
            dataset_id = item.get("dataset_id")
            try:
                self._run_pipeline(dataset_id, item)
            except Exception as exc:
                self.logger.exception(
                    f"{self.name}: error processing dataset_id={dataset_id}: {exc}"
                )

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(self, dataset_id: str, trigger_payload: dict) -> None:
        """Full UQ pipeline for one dataset_id."""
        self.logger.info(f"{self.name}: starting UQ pipeline for dataset_id={dataset_id}")

        # 1. Load parquet files
        unit_frames = self._load_processed_data(dataset_id)
        if not unit_frames:
            self.logger.error(
                f"{self.name}: no parquet data found for dataset_id={dataset_id}"
            )
            return

        # 2. Run MC Dropout inference per unit
        unit_predictions = self._run_mc_inference(unit_frames, dataset_id)
        self.logger.info(
            f"{self.name}: MC inference complete – {len(unit_predictions)} units"
        )

        # 3. Load ground-truth RUL (if available – test sets only)
        ground_truth = load_ground_truth_rul(dataset_id, self.raw_dir)

        # 4. Calibration analysis
        calibration = self._run_calibration(unit_predictions, ground_truth, dataset_id)

        # 5. Assemble result document
        result_doc = {
            "type": "UQ_RESULT",
            "dataset_id": dataset_id,
            "mc_samples": self.mc_samples,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "unit_predictions": unit_predictions,
            "calibration": calibration,
        }

        # 6. Persist to disk
        self._persist(dataset_id, result_doc)

        # 7. Publish to cmapss/risk
        publish_payload = {
            "type": "UQ_RESULT",
            "dataset_id": dataset_id,
            "mc_samples": self.mc_samples,
            "generated_at": result_doc["generated_at"],
            "n_units": len(unit_predictions),
            "ece": calibration.get("ece"),
            # Include per-unit predictions for downstream risk engine
            "unit_predictions": unit_predictions,
        }
        self.send_message(PUBLISH_TOPIC, publish_payload)
        self.logger.info(
            f"{self.name}: published UQ results for {dataset_id} → {PUBLISH_TOPIC}"
        )

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_processed_data(self, dataset_id: str) -> Dict[int, pd.DataFrame]:
        """
        Read all parquet files from ``data/processed/{dataset_id}/``.
        Returns a dict mapping unit_id → DataFrame.
        """
        data_dir = Path(self.processed_dir) / dataset_id
        if not data_dir.exists():
            self.logger.warning(f"{self.name}: directory not found: {data_dir}")
            return {}

        parquet_files = sorted(data_dir.glob("*.parquet"))
        if not parquet_files:
            self.logger.warning(f"{self.name}: no parquet files in {data_dir}")
            return {}

        unit_frames: Dict[int, pd.DataFrame] = {}
        for fp in parquet_files:
            try:
                df = pd.read_parquet(fp)
                # Determine unit_id: prefer column, fall back to filename
                if "unit_id" in df.columns and len(df["unit_id"].unique()) == 1:
                    uid = int(df["unit_id"].iloc[0])
                else:
                    # filename pattern: unit_XXXX.parquet
                    stem = fp.stem  # e.g. "unit_0001"
                    uid = int(stem.split("_")[-1])
                    if "unit_id" not in df.columns:
                        df = df.copy()
                        df["unit_id"] = uid
                unit_frames[uid] = df
            except Exception as exc:
                self.logger.warning(f"{self.name}: failed to read {fp}: {exc}")

        self.logger.info(
            f"{self.name}: loaded {len(unit_frames)} units from {data_dir}"
        )
        return unit_frames

    # ------------------------------------------------------------------
    # MC Dropout inference
    # ------------------------------------------------------------------

    def _run_mc_inference(
        self,
        unit_frames: Dict[int, pd.DataFrame],
        dataset_id: str,
    ) -> List[dict]:
        """
        Run MC Dropout inference for each engine unit.

        For every unit, calls ``ModelEngine.predict()`` with
        ``mc_samples=self.mc_samples`` (default 100) and collects:
        - ``rul_mean``      – posterior mean
        - ``rul_std``       – posterior standard deviation
        - ``ci_lower_90``   – 5th percentile (lower bound of 90% CI)
        - ``ci_upper_90``   – 95th percentile (upper bound of 90% CI)

        Returns list of per-unit dicts sorted by unit_id.
        """
        if self._engine is None:
            raise RuntimeError("ModelEngine not initialised. Call setup() first.")

        results: List[dict] = []
        for unit_id, df_unit in sorted(unit_frames.items()):
            try:
                preds = self._engine.predict(df_unit, mc_samples=self.mc_samples)
                results.append(
                    {
                        "unit_id": int(unit_id),
                        "rul_mean": round(preds["rul_mean"], 3),
                        "rul_std": round(preds["rul_std"], 3),
                        "ci_lower_90": round(preds["rul_lower"], 3),
                        "ci_upper_90": round(preds["rul_upper"], 3),
                        "dataset_id": dataset_id,
                    }
                )
            except Exception as exc:
                self.logger.warning(
                    f"{self.name}: inference failed for unit_id={unit_id}: {exc}"
                )

        return results

    # ------------------------------------------------------------------
    # Calibration analysis
    # ------------------------------------------------------------------

    def _run_calibration(
        self,
        unit_predictions: List[dict],
        ground_truth: Optional[Dict[int, float]],
        dataset_id: str,
    ) -> dict:
        """
        Compute ECE and reliability diagram data.

        Requires ground-truth RUL values (only available for test datasets).
        If ground_truth is None, returns a metadata-only dict.
        """
        if ground_truth is None:
            self.logger.info(
                f"{self.name}: no ground-truth RUL for {dataset_id} – "
                "calibration skipped (training split)"
            )
            return {
                "available": False,
                "reason": "No ground-truth RUL file found (training dataset).",
            }

        intervals: List[Tuple[float, float]] = []
        actuals: List[float] = []

        for pred in unit_predictions:
            uid = pred["unit_id"]
            if uid in ground_truth:
                intervals.append(
                    (pred["ci_lower_90"], pred["ci_upper_90"])
                )
                actuals.append(float(ground_truth[uid]))

        if len(actuals) == 0:
            self.logger.warning(
                f"{self.name}: no unit_id overlap between predictions and "
                "ground truth – calibration skipped."
            )
            return {
                "available": False,
                "reason": "No unit_id overlap between predictions and ground-truth RUL.",
            }

        ece, diagram_data = compute_ece(intervals, actuals)

        # Coverage at 90% CI
        coverage_90 = sum(
            1 for (lo, hi), a in zip(intervals, actuals) if lo <= a <= hi
        ) / len(actuals)

        # Mean interval width
        mean_width = float(
            np.mean([hi - lo for (lo, hi) in intervals])
        )

        calibration = {
            "available": True,
            "n_units_evaluated": len(actuals),
            "ece": round(ece, 6),
            "coverage_90pct": round(coverage_90, 4),
            "mean_ci_width": round(mean_width, 3),
            "reliability_diagram": diagram_data,
        }

        self.logger.info(
            f"{self.name}: calibration – ECE={ece:.4f}  "
            f"coverage_90%={coverage_90:.3f}  mean_ci_width={mean_width:.1f}"
        )
        return calibration

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, dataset_id: str, result_doc: dict) -> None:
        """Save the full result document to data/results/uncertainty_{dataset_id}.json."""
        out_path = Path(self.results_dir) / f"uncertainty_{dataset_id}.json"
        with open(out_path, "w") as fh:
            json.dump(result_doc, fh, indent=2)
        self.logger.info(f"{self.name}: results persisted → {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("\n" + "=" * 65)
    print("📊 [UNCERTAINTY QUANTIFICATION CONTAINER ONLINE]")
    print(f"   Subscribe: {SUBSCRIBE_TOPIC}")
    print(f"   Publish  : {PUBLISH_TOPIC}")
    print(f"   MC samples: {MC_SAMPLES}")
    print("=" * 65 + "\n")

    component = UncertaintyQuantification()
    component.setup()

    try:
        while True:
            component.execute()
            time.sleep(0.5)
    except KeyboardInterrupt:
        component.teardown()
        logging.getLogger(__name__).info("🛑 UncertaintyQuantification stopped")

