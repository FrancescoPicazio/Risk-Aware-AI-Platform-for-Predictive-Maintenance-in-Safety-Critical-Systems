"""
Monitoring & Drift Module
==========================
Production-grade monitoring component for the Risk-Aware Prognostics Platform.

Architecture (§4.10 ARCHITECTURE.md)
--------------------------------------
Responsibilities
    1. Data drift detection    – KS test (scipy.stats.ks_2samp) per feature,
                                 comparing training reference vs. incoming streaming data.
    2. Performance drift       – rolling RMSE and NASA score; alert if Δ > 10 %.
    3. Calibration drift       – track ECE from uncertainty_*.json over time.
    4. Retraining trigger      – publish to cmapss/training if drift_score > DRIFT_THRESHOLD.
    5. Model version tracking  – read/write data/model_artifacts/model_registry.json.

MQTT
    Subscribe : ``cmapss/monitoring``  (ECONOMIC_SUMMARY, RUL_PREDICTION, TRAINING_COMPLETE)
                ``cmapss/scheduler``   (type=MONITORING for scheduled reports)
    Publish   : ``cmapss/training``    (RETRAIN_REQUEST when drift exceeds threshold)

Output files
    data/metrics_and_results/monitoring_report_{timestamp}.json
    data/model_artifacts/model_registry.json

FastAPI sub-app (optional, port 8001)
    GET /drift          – latest drift report
    GET /model-versions – model registry contents

Environment variables
    DRIFT_THRESHOLD   float  default 0.15   KS-stat threshold triggering retraining
    PERF_DELTA_PCT    float  default 10.0   % RMSE/NASA degradation triggering alert
    ROLLING_WINDOW    int    default 50     predictions in the rolling performance window
    ENABLE_API        bool   default true   whether to start the FastAPI sub-app
    API_PORT          int    default 8001
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from configs import config
from src.common.components import PipelineComponent

# ---------------------------------------------------------------------------
# Optional scipy – KS test
# ---------------------------------------------------------------------------
_ks_2samp = None
SCIPY_AVAILABLE = False
try:
    from scipy.stats import ks_2samp as _ks_2samp  # type: ignore[assignment]
    SCIPY_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning(
        "scipy not available – KS test disabled, falling back to mean-shift drift."
    )

# ---------------------------------------------------------------------------
# MQTT topics
# ---------------------------------------------------------------------------
SUBSCRIBE_TOPICS: List[str] = [
    config.MQTT["TOPICS"]["MONITORING"],
    config.MQTT["TOPICS"]["SCHEDULER"],
    config.MQTT["TOPICS"]["INFERENCE"],
]
PUBLISH_TRAINING_TOPIC: str = config.MQTT["TOPICS"]["TRAINING"]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_OUTPUT_DIR: Path = Path(
    config.DATA.get("METRICS_AND_RESULTS", "data/metrics_and_results")
)
_PROCESSED_DIR: Path = Path(config.DATA["PROCESSED"])
_ARTIFACTS_DIR: Path = Path(config.DATA["MODEL_ARTIFACTS"])
_MODEL_REGISTRY_FILE: Path = _ARTIFACTS_DIR / "model_registry.json"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_DRIFT_THRESHOLD: float = 0.15
_DEFAULT_PERF_DELTA_PCT: float = 10.0
_DEFAULT_ROLLING_WINDOW: int = 50

logger = logging.getLogger(__name__)


# ===========================================================================
# NASA scoring function
# ===========================================================================

def nasa_score(errors: np.ndarray) -> float:
    """
    NASA asymmetric scoring function for RUL prediction.
    s = sum(exp(-e/13) - 1  if e < 0,
            exp( e/10) - 1  if e >= 0)
    """
    scores = np.where(
        errors < 0,
        np.exp(-errors / 13.0) - 1.0,
        np.exp(errors / 10.0) - 1.0,
    )
    return float(np.mean(scores))


# ===========================================================================
# KS-based data drift detection
# ===========================================================================

def ks_drift_report(
    reference: pd.DataFrame,
    incoming: pd.DataFrame,
    feature_cols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run a two-sample KS test for each numeric feature column.

    Parameters
    ----------
    reference    : training reference dataset (from data/processed/)
    incoming     : streaming / recent data
    feature_cols : explicit list of columns; if None, uses numeric intersection

    Returns
    -------
    dict with keys:
        features   : {col: {ks_stat, p_value, drifted}} per feature
        max_ks     : max KS statistic across all features
        mean_ks    : mean KS statistic
        n_drifted  : number of features with drift
        drift_score: mean_ks (used as the aggregate drift signal)
    """
    if feature_cols is None:
        num_ref = set(reference.select_dtypes(include=[np.number]).columns)
        num_inc = set(incoming.select_dtypes(include=[np.number]).columns)
        # exclude meta-columns
        exclude = {"unit_id", "cycle", "RUL", "rul", "time"}
        feature_cols = sorted((num_ref & num_inc) - exclude)

    feature_results: Dict[str, dict] = {}
    ks_stats: List[float] = []

    for col in feature_cols:
        ref_vals = reference[col].dropna().values
        inc_vals = incoming[col].dropna().values
        if len(ref_vals) < 5 or len(inc_vals) < 5:
            continue

        if SCIPY_AVAILABLE and _ks_2samp is not None:
            stat, p_val = _ks_2samp(ref_vals, inc_vals)
        else:
            # Fallback: normalised absolute mean shift
            ref_std = float(np.std(ref_vals)) or 1.0
            stat = abs(float(np.mean(ref_vals)) - float(np.mean(inc_vals))) / ref_std
            p_val = float("nan")

        ks_stats.append(stat)
        feature_results[col] = {
            "ks_stat": round(float(stat), 6),
            "p_value": round(float(p_val), 6) if not np.isnan(p_val) else None,
            "drifted": bool(stat > _DEFAULT_DRIFT_THRESHOLD),
        }

    if not ks_stats:
        return {
            "features": {},
            "max_ks": 0.0,
            "mean_ks": 0.0,
            "n_drifted": 0,
            "drift_score": 0.0,
        }

    return {
        "features": feature_results,
        "max_ks": round(float(np.max(ks_stats)), 6),
        "mean_ks": round(float(np.mean(ks_stats)), 6),
        "n_drifted": sum(1 for v in feature_results.values() if v["drifted"]),
        "drift_score": round(float(np.mean(ks_stats)), 6),
    }


# ===========================================================================
# Performance drift tracking
# ===========================================================================

class RollingPerformanceTracker:
    """
    Maintains a rolling window of RMSE and NASA score values and detects
    degradation relative to the baseline (first full window).
    """

    def __init__(self, window: int = _DEFAULT_ROLLING_WINDOW):
        self._window = window
        self._errors: deque = deque(maxlen=window * 3)
        self._baseline_rmse: Optional[float] = None
        self._baseline_nasa: Optional[float] = None

    def add(self, rul_pred: float, rul_true: float) -> None:
        self._errors.append(float(rul_pred) - float(rul_true))

    def metrics(self) -> Dict[str, Any]:
        errors = np.array(list(self._errors))
        if len(errors) < 2:
            return {"available": False}

        current_rmse = float(np.sqrt(np.mean(errors ** 2)))
        current_nasa = nasa_score(errors)

        # Seed baseline on first full window
        if self._baseline_rmse is None and len(errors) >= self._window:
            self._baseline_rmse = current_rmse
            self._baseline_nasa = current_nasa

        result: Dict[str, Any] = {
            "available": True,
            "n_samples": len(errors),
            "current_rmse": round(current_rmse, 4),
            "current_nasa_score": round(current_nasa, 4),
            "baseline_rmse": round(self._baseline_rmse, 4) if self._baseline_rmse else None,
            "baseline_nasa_score": round(self._baseline_nasa, 4) if self._baseline_nasa else None,
        }

        if self._baseline_rmse and self._baseline_rmse > 0:
            delta_rmse_pct = 100.0 * (current_rmse - self._baseline_rmse) / self._baseline_rmse
            result["delta_rmse_pct"] = round(delta_rmse_pct, 2)
            result["rmse_degraded"] = delta_rmse_pct > _DEFAULT_PERF_DELTA_PCT

        if self._baseline_nasa and self._baseline_nasa != 0:
            delta_nasa_pct = 100.0 * (current_nasa - self._baseline_nasa) / abs(self._baseline_nasa)
            result["delta_nasa_pct"] = round(delta_nasa_pct, 2)
            result["nasa_degraded"] = delta_nasa_pct > _DEFAULT_PERF_DELTA_PCT

        return result


# ===========================================================================
# Calibration drift
# ===========================================================================

def load_latest_ece(output_dir: Path) -> Optional[Dict]:
    """
    Read all uncertainty_*.json files and return a time-series of ECE values.
    """
    ece_history: List[Dict] = []
    for fp in sorted(output_dir.glob("uncertainty_*.json")):
        try:
            with open(fp) as f:
                doc = json.load(f)
            cal = doc.get("calibration", {})
            if cal.get("available") and "ece" in cal:
                ece_history.append(
                    {
                        "dataset_id": doc.get("dataset_id", fp.stem),
                        "ece": cal["ece"],
                        "coverage_90pct": cal.get("coverage_90pct"),
                        "generated_at": doc.get("generated_at"),
                    }
                )
        except Exception as exc:
            logger.debug(f"Could not parse {fp.name}: {exc}")

    if len(ece_history) < 2:
        return {"available": False, "history": ece_history}

    eces = [e["ece"] for e in ece_history]
    latest_ece = eces[-1]
    baseline_ece = eces[0]
    delta_pct = (
        100.0 * (latest_ece - baseline_ece) / baseline_ece
        if baseline_ece > 0
        else 0.0
    )
    return {
        "available": True,
        "latest_ece": round(latest_ece, 6),
        "baseline_ece": round(baseline_ece, 6),
        "delta_ece_pct": round(delta_pct, 2),
        "ece_degraded": delta_pct > _DEFAULT_PERF_DELTA_PCT,
        "history": ece_history,
    }


# ===========================================================================
# Model registry
# ===========================================================================

def load_model_registry(registry_path: Path) -> List[Dict]:
    if not registry_path.exists():
        return []
    try:
        with open(registry_path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    except Exception as exc:
        logger.warning(f"Could not read model registry: {exc}")
        return []


def register_model(registry_path: Path, model_record: dict) -> None:
    """Append a model record to model_registry.json."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_model_registry(registry_path)
    # Avoid duplicate run_ids
    run_id = model_record.get("run_id")
    if run_id and any(r.get("run_id") == run_id for r in existing):
        return
    existing.append(
        {**model_record, "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    )
    with open(registry_path, "w") as f:
        json.dump(existing, f, indent=2)


# ===========================================================================
# Reference data loader
# ===========================================================================

def load_reference_data(processed_dir: Path) -> Optional[pd.DataFrame]:
    """Load all processed parquet files as the training reference distribution."""
    files = sorted(processed_dir.rglob("*.parquet"))
    if not files:
        return None
    frames = []
    for fp in files:
        try:
            frames.append(pd.read_parquet(fp))
        except Exception as exc:
            logger.debug(f"Could not read {fp}: {exc}")
    return pd.concat(frames, ignore_index=True) if frames else None


# ===========================================================================
# PipelineComponent
# ===========================================================================

class MonitoringDriftModule(PipelineComponent):
    """
    Monitoring & Drift Detection Module (§4.10 ARCHITECTURE.md).

    Subscribe : ``cmapss/monitoring``, ``cmapss/scheduler``, ``cmapss/inference``
    Publish   : ``cmapss/training``  (retraining trigger when drift > threshold)

    Output    : data/metrics_and_results/monitoring_report_{timestamp}.json
                data/model_artifacts/model_registry.json
    """

    def __init__(
        self,
        drift_threshold: float = _DEFAULT_DRIFT_THRESHOLD,
        perf_delta_pct: float = _DEFAULT_PERF_DELTA_PCT,
        rolling_window: int = _DEFAULT_ROLLING_WINDOW,
        output_dir: Optional[str] = None,
        processed_dir: Optional[str] = None,
        artifacts_dir: Optional[str] = None,
    ):
        super().__init__(
            name="MonitoringDriftModule",
            mqtt_topic_subscribe_list=SUBSCRIBE_TOPICS,
        )
        self._drift_threshold: float = float(
            os.getenv("DRIFT_THRESHOLD", str(drift_threshold))
        )
        self._perf_delta_pct: float = float(
            os.getenv("PERF_DELTA_PCT", str(perf_delta_pct))
        )
        self._rolling_window: int = int(
            os.getenv("ROLLING_WINDOW", str(rolling_window))
        )
        self._output_dir: Path = Path(output_dir or str(_OUTPUT_DIR))
        self._processed_dir: Path = Path(processed_dir or str(_PROCESSED_DIR))
        self._artifacts_dir: Path = Path(artifacts_dir or str(_ARTIFACTS_DIR))
        self._registry_path: Path = self._artifacts_dir / "model_registry.json"

        # State
        self._perf_tracker = RollingPerformanceTracker(self._rolling_window)
        self._reference_df: Optional[pd.DataFrame] = None
        self._incoming_buffer: deque = deque(maxlen=500)  # raw feature rows
        self._report_requested: bool = False
        self._latest_report: Optional[Dict] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        super().setup()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Load training reference distribution at startup
        self._reference_df = load_reference_data(self._processed_dir)
        if self._reference_df is not None:
            logger.info(
                f"{self.name}: reference data loaded – "
                f"{len(self._reference_df)} rows, "
                f"{len(self._reference_df.columns)} cols"
            )
        else:
            logger.warning(
                f"{self.name}: no reference data found in {self._processed_dir}"
            )

        logger.info(
            f"{self.name}: ready — "
            f"DRIFT_THRESHOLD={self._drift_threshold}  "
            f"PERF_DELTA_PCT={self._perf_delta_pct}%  "
            f"ROLLING_WINDOW={self._rolling_window}"
        )

    def teardown(self) -> None:
        super().teardown()
        logger.info(f"{self.name}: teardown complete")

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def on_message_received(self, payload: dict) -> None:
        msg_type = payload.get("type", "")

        if msg_type == "MONITORING" or (
            msg_type == "" and payload.get("trigger") == "monitoring"
        ):
            logger.info(f"{self.name}: monitoring report requested via MQTT")
            self._report_requested = True

        elif msg_type == "ECONOMIC_SUMMARY":
            # Triggered by EconomicOptimizationLayer output on cmapss/monitoring
            logger.info(f"{self.name}: economic summary received – scheduling report")
            self._report_requested = True

        elif msg_type == "RUL_PREDICTION":
            self._handle_rul_prediction(payload)

        elif msg_type == "TRAINING_COMPLETE":
            self._handle_training_complete(payload)

        elif msg_type == "FEATURES_READY":
            # Feature Engineering published new processed rows; use as streaming sample
            unit_id = payload.get("unit_id")
            logger.debug(f"{self.name}: FEATURES_READY unit={unit_id}")

    def _handle_rul_prediction(self, payload: dict) -> None:
        rul_mean = payload.get("rul_mean")
        rul_true = payload.get("rul_true")  # may not be present in prod
        if rul_mean is not None:
            if rul_true is not None:
                self._perf_tracker.add(float(rul_mean), float(rul_true))
            # Also store the raw feature snapshot if available
            feature_row = payload.get("features")
            if feature_row and isinstance(feature_row, dict):
                self._incoming_buffer.append(feature_row)

    def _handle_training_complete(self, payload: dict) -> None:
        run_id = payload.get("run_id")
        logger.info(
            f"{self.name}: new model registered – run_id={run_id} "
            f"RMSE={payload.get('rmse')}"
        )
        register_model(self._registry_path, payload)

    # ------------------------------------------------------------------
    # Main loop
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
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        logger.info(f"{self.name}: generating monitoring report {timestamp}…")

        # 1. Data drift (KS test)
        data_drift = self._compute_data_drift()

        # 2. Performance drift
        perf_drift = self._perf_tracker.metrics()
        # Override delta_pct threshold with configured value
        if "delta_rmse_pct" in perf_drift:
            perf_drift["rmse_degraded"] = (
                perf_drift["delta_rmse_pct"] > self._perf_delta_pct
            )
        if "delta_nasa_pct" in perf_drift:
            perf_drift["nasa_degraded"] = (
                perf_drift["delta_nasa_pct"] > self._perf_delta_pct
            )

        # 3. Calibration drift (ECE)
        cal_drift = load_latest_ece(self._output_dir)

        # 4. Model registry snapshot
        registry = load_model_registry(self._registry_path)

        # 5. Aggregate drift score
        drift_score = data_drift.get("drift_score", 0.0)
        perf_degraded = perf_drift.get("rmse_degraded", False) or perf_drift.get(
            "nasa_degraded", False
        )
        cal_degraded = cal_drift.get("ece_degraded", False) if cal_drift else False

        retrain_triggered = (
            drift_score > self._drift_threshold
            or perf_degraded
            or cal_degraded
        )

        report = {
            "type": "MONITORING_REPORT",
            "timestamp": timestamp,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "drift_threshold": self._drift_threshold,
            "perf_delta_pct_threshold": self._perf_delta_pct,
            # Section 1: data drift
            "data_drift": data_drift,
            # Section 2: performance drift
            "performance_drift": perf_drift,
            # Section 3: calibration drift
            "calibration_drift": cal_drift,
            # Section 4: model registry (latest 5 entries)
            "model_registry_latest": registry[-5:] if registry else [],
            "n_registered_models": len(registry),
            # Section 5: overall verdict
            "retrain_triggered": retrain_triggered,
            "retrain_reason": self._retrain_reason(
                drift_score, perf_degraded, cal_degraded
            ),
        }

        self._latest_report = report

        # Persist
        out_path = self._output_dir / f"monitoring_report_{timestamp}.json"
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"{self.name}: report saved → {out_path.name}")

        # Log summary
        self._log_report_summary(report)

        # 6. Retraining trigger
        if retrain_triggered:
            self._trigger_retraining(report)

    def _compute_data_drift(self) -> Dict:
        """Run KS drift detection between reference and incoming buffer."""
        if self._reference_df is None or not self._incoming_buffer:
            return {
                "available": False,
                "reason": "No reference data or no incoming samples yet.",
                "drift_score": 0.0,
            }

        try:
            incoming_df = pd.DataFrame(list(self._incoming_buffer))
            result = ks_drift_report(self._reference_df, incoming_df)
            result["n_incoming_samples"] = len(incoming_df)
            result["available"] = True
            return result
        except Exception as exc:
            logger.warning(f"{self.name}: KS drift computation failed: {exc}")
            return {"available": False, "reason": str(exc), "drift_score": 0.0}

    def _retrain_reason(
        self,
        drift_score: float,
        perf_degraded: bool,
        cal_degraded: bool,
    ) -> Optional[str]:
        reasons = []
        if drift_score > self._drift_threshold:
            reasons.append(
                f"data_drift={drift_score:.4f} > threshold={self._drift_threshold}"
            )
        if perf_degraded:
            reasons.append("performance_degradation > threshold")
        if cal_degraded:
            reasons.append("calibration_degradation > threshold")
        return "; ".join(reasons) if reasons else None

    def _trigger_retraining(self, report: dict) -> None:
        payload = {
            "type": "TRAINING",
            "trigger": "drift_monitor",
            "reason": report.get("retrain_reason"),
            "drift_score": report["data_drift"].get("drift_score"),
            "timestamp": time.time(),
        }
        sent = self.send_message(PUBLISH_TRAINING_TOPIC, payload)
        if sent:
            logger.warning(
                f"{self.name}: 🔁 RETRAINING TRIGGERED — "
                f"{report.get('retrain_reason')}"
            )

    def _log_report_summary(self, report: dict) -> None:
        dd = report["data_drift"]
        pd_ = report["performance_drift"]
        cd = report.get("calibration_drift") or {}
        logger.info(
            f"{self.name}: report summary — "
            f"drift_score={dd.get('drift_score', 'n/a')}  "
            f"n_drifted_features={dd.get('n_drifted', 'n/a')}  "
            f"rmse={pd_.get('current_rmse', 'n/a')}  "
            f"ece={cd.get('latest_ece', 'n/a')}  "
            f"retrain={'⚠️ YES' if report['retrain_triggered'] else 'NO'}"
        )
        if report["retrain_triggered"]:
            logger.warning(
                f"{self.name}: ⚠️  DRIFT DETECTED — {report.get('retrain_reason')}"
            )

    # ------------------------------------------------------------------
    # Public API for FastAPI sub-app
    # ------------------------------------------------------------------

    def get_latest_report(self) -> Optional[Dict]:
        return self._latest_report

    def get_registry(self) -> List[Dict]:
        return load_model_registry(self._registry_path)


# ===========================================================================
# Optional FastAPI sub-app
# ===========================================================================

def _read_report_from_disk(component: "MonitoringDriftModule") -> Optional[Dict]:
    """Load the most recent report file from disk (sync helper)."""
    reports = sorted(component._output_dir.glob("monitoring_report_*.json"))
    if not reports:
        return None
    try:
        with open(reports[-1]) as f:
            return json.load(f)
    except Exception:
        return None


def _read_report_history(
    component: "MonitoringDriftModule", limit: int
) -> List[Dict]:
    """Load the last N report files from disk (sync helper)."""
    files = sorted(component._output_dir.glob("monitoring_report_*.json"))[-limit:]
    history = []
    for fp in files:
        try:
            with open(fp) as f:
                history.append(json.load(f))
        except Exception:
            pass
    return history


def build_monitoring_api(component: "MonitoringDriftModule"):
    """
    Build a minimal FastAPI app exposing /drift and /model-versions.
    Mounted on port API_PORT (default 8001).
    """
    try:
        from fastapi import FastAPI
        from fastapi.concurrency import run_in_threadpool
    except ImportError:
        logger.warning("FastAPI not available – monitoring API disabled.")
        return None

    monitoring_app = FastAPI(
        title="Monitoring & Drift API",
        description="Exposes drift reports and model version tracking.",
        version="1.0.0",
    )

    @monitoring_app.get("/health")
    async def health():
        return {"status": "healthy", "service": "monitoring-drift-api"}

    @monitoring_app.get("/drift")
    async def get_drift():
        """Return the latest drift monitoring report."""
        report = component.get_latest_report()
        if report is None:
            report = await run_in_threadpool(_read_report_from_disk, component)
        if report is None:
            return {"status": "no_report_yet"}
        return report

    @monitoring_app.get("/model-versions")
    async def get_model_versions():
        """Return all model versions from model_registry.json."""
        registry = await run_in_threadpool(component.get_registry)
        return {
            "n_versions": len(registry),
            "registry": registry,
            "registry_path": str(component._registry_path),
        }

    @monitoring_app.get("/drift/history")
    async def drift_history(limit: int = 20):
        """Return the last N monitoring reports from disk."""
        history = await run_in_threadpool(_read_report_history, component, limit)
        return {"n_reports": len(history), "reports": history}

    return monitoring_app


def _start_api_server(component: MonitoringDriftModule, port: int) -> None:
    """Run the FastAPI sub-app in a background daemon thread."""
    app = build_monitoring_api(component)
    if app is None:
        return
    try:
        import uvicorn
        host = os.getenv("API_HOST", "0.0.0.0")  # nosec B104 – intentional in container
        logger.info(
            f"MonitoringDriftModule: starting FastAPI sub-app on {host}:{port}"
        )
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except Exception as exc:
        logger.error(f"Monitoring API failed to start: {exc}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    _dt = float(os.getenv("DRIFT_THRESHOLD", str(_DEFAULT_DRIFT_THRESHOLD)))
    _dp = float(os.getenv("PERF_DELTA_PCT", str(_DEFAULT_PERF_DELTA_PCT)))
    _rw = int(os.getenv("ROLLING_WINDOW", str(_DEFAULT_ROLLING_WINDOW)))
    _enable_api = os.getenv("ENABLE_API", "true").lower() in ("1", "true", "yes")
    _api_port = int(os.getenv("API_PORT", "8001"))

    print("\n" + "=" * 65)
    print("📈 [MONITORING & DRIFT MODULE CONTAINER ONLINE]")
    print(f"   Subscribe       : {', '.join(SUBSCRIBE_TOPICS)}")
    print(f"   Publish (retrain): {PUBLISH_TRAINING_TOPIC}")
    print(f"   DRIFT_THRESHOLD : {_dt}")
    print(f"   PERF_DELTA_PCT  : {_dp}%")
    print(f"   ROLLING_WINDOW  : {_rw}")
    print(f"   FastAPI sub-app : {'enabled on :' + str(_api_port) if _enable_api else 'disabled'}")
    print("=" * 65 + "\n")

    component = MonitoringDriftModule(
        drift_threshold=_dt,
        perf_delta_pct=_dp,
        rolling_window=_rw,
    )
    component.setup()

    # Start optional FastAPI sub-app in background thread
    if _enable_api:
        api_thread = threading.Thread(
            target=_start_api_server,
            args=(component, _api_port),
            daemon=True,
        )
        api_thread.start()

    try:
        while True:
            component.execute()
            time.sleep(1.0)
    except KeyboardInterrupt:
        component.teardown()
        logging.getLogger(__name__).info("🛑 MonitoringDriftModule stopped")

