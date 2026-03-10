"""
Inference API – FastAPI
========================
Standalone REST API for the Risk-Aware Prognostics Platform.

Architecture (§4.9 ARCHITECTURE.md)
-------------------------------------
Endpoints
    POST /predict   – MC-Dropout RUL inference for a single engine unit
    GET  /risk      – Latest risk score + maintenance urgency for all units
    GET  /health    – Liveness check: status, model_version, uptime
    GET  /metrics   – RMSE, NASA score, ECE from latest evaluation

Design decisions
-----------------
* Model is loaded **at startup** via ``ModelEngine.load_best()`` (eager load).
  A background reload fires every MODEL_RELOAD_INTERVAL seconds so a
  newly-trained model is picked up without restarting the container.
* ``POST /predict`` accepts ``{unit_id, sensor_data[]}`` where
  ``sensor_data`` is an ordered list of ``{name, value}`` objects.
  If parquet data for the unit is available it is used preferentially.
* ``GET /risk`` aggregates the *latest* record per unit from
  ``risk_decisions.json`` and ``uncertainty_{dataset_id}.json`` files.
* ``GET /metrics`` merges training metrics (RMSE, NASA) with the ECE from
  the latest UQ calibration result.

Paths searched (in priority order):
    data/results/              – primary (written by all pipeline components)
    data/metrics_and_results/  – alternate path mentioned in requirements
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from configs import config
from src.model.model_engine import ModelEngine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup timestamp (for uptime)
# ---------------------------------------------------------------------------
_START_TIME: float = time.time()

# ---------------------------------------------------------------------------
# Paths – support both naming conventions
# ---------------------------------------------------------------------------
_RESULTS_CANDIDATES: List[Path] = [
    Path(os.getenv("RESULTS_DIR", config.DATA["RESULTS"])),
    Path("data/metrics_and_results"),
]
PROCESSED_DIR: Path = Path(os.getenv("PROCESSED_DIR", config.DATA["PROCESSED"]))
MODEL_ARTIFACTS_DIR: Path = Path(os.getenv("MODEL_PATH", config.DATA["MODEL_ARTIFACTS"]))

# Result file names
_METRICS_FILE = "model_metrics.json"
_RISK_FILE = "risk_decisions.json"
_UQ_PREFIX = "uncertainty_"   # uncertainty_{dataset_id}.json

# ---------------------------------------------------------------------------
# Model engine – loaded at startup, reloaded in background
# ---------------------------------------------------------------------------
_engine: Optional[ModelEngine] = None
_engine_lock = threading.Lock()
_MODEL_RELOAD_INTERVAL: float = float(os.getenv("MODEL_RELOAD_INTERVAL", "300"))
_model_version: str = "unknown"


def _primary_results_dir() -> Path:
    for p in _RESULTS_CANDIDATES:
        if p.exists():
            return p
    _RESULTS_CANDIDATES[0].mkdir(parents=True, exist_ok=True)
    return _RESULTS_CANDIDATES[0]


def _read_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    except Exception as exc:
        logger.warning(f"Could not read {path}: {exc}")
        return []


def _read_all_uncertainty_records() -> List[dict]:
    """
    Flatten all uncertainty_{dataset_id}.json files into a list of
    per-unit prediction dicts.  Also reads the legacy uncertainty_results.json.
    """
    results_dir = _primary_results_dir()
    all_records: List[dict] = []

    for uq_file in results_dir.glob(f"{_UQ_PREFIX}*.json"):
        try:
            with open(uq_file) as f:
                doc = json.load(f)
            if isinstance(doc, dict) and "unit_predictions" in doc:
                for unit_pred in doc["unit_predictions"]:
                    enriched = dict(unit_pred)
                    enriched.setdefault("dataset_id", doc.get("dataset_id", ""))
                    enriched.setdefault("generated_at", doc.get("generated_at", ""))
                    all_records.append(enriched)
            elif isinstance(doc, list):
                all_records.extend(doc)
        except Exception as exc:
            logger.warning(f"Could not parse {uq_file}: {exc}")

    # legacy flat-list file from UncertaintyAndFailure component
    legacy = results_dir / "uncertainty_results.json"
    if legacy.exists():
        all_records.extend(_read_json(legacy))

    return all_records


def _load_engine() -> None:
    global _engine, _model_version
    with _engine_lock:
        try:
            eng = ModelEngine(
                artifacts_dir=str(MODEL_ARTIFACTS_DIR),
                results_dir=str(_primary_results_dir()),
            )
            loaded = eng.load_best()
            _engine = eng
            if loaded:
                best = eng.metrics_store.best_model()
                _model_version = best.get("run_id", "unknown") if best else "unknown"
                logger.info(f"API: model loaded – version={_model_version}")
            else:
                _model_version = "no_model"
                logger.warning("API: no trained model available at startup")
        except Exception as exc:
            logger.error(f"API: model load failed: {exc}")


def _background_reload(interval: float) -> None:
    while True:
        time.sleep(interval)
        logger.info("API: background model reload triggered")
        _load_engine()


def _load_parquet_for_unit(unit_id: int) -> Optional[pd.DataFrame]:
    pattern = f"unit_{unit_id:04d}.parquet"
    files = list(PROCESSED_DIR.rglob(pattern))
    if not files:
        files = list(PROCESSED_DIR.rglob("*.parquet"))
        frames = []
        for fp in files:
            try:
                df = pd.read_parquet(fp)
                if "unit_id" in df.columns:
                    filtered = df[df["unit_id"] == unit_id]
                    if not filtered.empty:
                        frames.append(filtered)
            except Exception:
                pass
        return pd.concat(frames, ignore_index=True) if frames else None
    frames = []
    for fp in files:
        try:
            frames.append(pd.read_parquet(fp))
        except Exception as exc:
            logger.warning(f"Could not read {fp}: {exc}")
    return pd.concat(frames, ignore_index=True) if frames else None


def _sensor_data_to_df(
    unit_id: int,
    sensor_readings: "List[SensorReading]",
    feature_cols: List[str],
) -> pd.DataFrame:
    reading_map: Dict[str, float] = {sr.name: sr.value for sr in sensor_readings}
    row: Dict[str, Any] = {"unit_id": unit_id, "cycle": 1}
    for col in feature_cols:
        row[col] = reading_map.get(col, 0.0)
    return pd.DataFrame([row])


def _latest_per_unit(records: List[dict]) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for r in records:
        uid = r.get("unit_id")
        if uid is not None:
            out[int(uid)] = r
    return out


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Risk-Aware Prognostics API",
    description=(
        "Real-time RUL inference, uncertainty quantification, risk assessment "
        "and economic decision support for safety-critical predictive maintenance."
    ),
    version="1.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("API: startup – loading model…")
    _load_engine()
    t = threading.Thread(
        target=_background_reload,
        args=(_MODEL_RELOAD_INTERVAL,),
        daemon=True,
    )
    t.start()
    logger.info(f"API: background model reload every {_MODEL_RELOAD_INTERVAL}s started")


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class SensorReading(BaseModel):
    """A single named sensor value."""
    name: str = Field(..., description="Sensor or feature name, e.g. 'sensor_2'")
    value: float = Field(..., description="Current reading")


class PredictRequest(BaseModel):
    unit_id: int = Field(..., description="Engine unit identifier", examples=[1])
    sensor_data: Optional[List[SensorReading]] = Field(
        default=None,
        description=(
            "Ordered list of sensor readings.  If omitted the API reads "
            "the latest processed parquet for this unit."
        ),
    )


class ConfidenceInterval(BaseModel):
    lower: float = Field(..., description="5th-percentile RUL (90% CI lower bound)")
    upper: float = Field(..., description="95th-percentile RUL (90% CI upper bound)")
    coverage: float = Field(0.90, description="Nominal coverage probability")


class PredictResponse(BaseModel):
    unit_id: int
    rul_mean: float = Field(..., description="Posterior mean RUL (cycles)")
    rul_std: float = Field(..., description="Posterior standard deviation")
    confidence_interval: ConfidenceInterval
    uncertainty_score: float = Field(
        ..., description="Coefficient of variation: std / max(mean, 1)"
    )
    mc_samples: int = Field(..., description="MC Dropout forward passes used")
    source: str


class RiskUnitResponse(BaseModel):
    unit_id: int
    risk_score: float
    maintenance_urgency: str
    failure_probability: float
    rul_mean: float
    rul_std: float
    recommended_action: str
    intervention_window_cycles: int
    expected_cost_eur: float
    cost_savings_vs_reactive_eur: float
    alert_level: str
    dataset_id: Optional[str] = None
    timestamp: Optional[Any] = None


class HealthResponse(BaseModel):
    status: str
    model_version: str
    uptime_seconds: float
    model_artifacts_dir: str
    results_dir: str


class MetricsResponse(BaseModel):
    rmse: Optional[float] = None
    nasa_score: Optional[float] = None
    ece: Optional[float] = None
    coverage_90pct: Optional[float] = None
    model_version: Optional[str] = None
    trained_at: Optional[str] = None
    total_training_runs: int = 0
    calibration_available: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "service": "Risk-Aware Prognostics API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
        "endpoints": [
            "POST /predict",
            "GET  /risk",
            "GET  /health",
            "GET  /metrics",
        ],
    }


# ── GET /health ──────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Liveness probe.

    Returns
    -------
    status         – always "healthy" while the container is running
    model_version  – run_id of the loaded model artifact ("no_model" if absent)
    uptime_seconds – seconds since container startup
    """
    return HealthResponse(
        status="healthy",
        model_version=_model_version,
        uptime_seconds=round(time.time() - _START_TIME, 1),
        model_artifacts_dir=str(MODEL_ARTIFACTS_DIR),
        results_dir=str(_primary_results_dir()),
    )


# ── GET /metrics ─────────────────────────────────────────────────────────────

@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """
    Latest evaluation metrics: RMSE and NASA score (from training) + ECE
    and 90% coverage (from the latest UQ calibration run).
    """
    results_dir = _primary_results_dir()

    # Training metrics
    training_records = _read_json(results_dir / _METRICS_FILE)
    best_training: Optional[dict] = None
    if training_records:
        best_training = min(
            training_records, key=lambda r: r.get("rmse", float("inf"))
        )

    # Calibration (ECE) from latest uncertainty_{dataset_id}.json
    ece: Optional[float] = None
    coverage: Optional[float] = None
    calibration_available = False

    uq_files = sorted(results_dir.glob(f"{_UQ_PREFIX}*.json"))
    if uq_files:
        try:
            with open(uq_files[-1]) as f:
                uq_doc = json.load(f)
            cal = uq_doc.get("calibration", {})
            if cal.get("available"):
                ece = cal.get("ece")
                coverage = cal.get("coverage_90pct")
                calibration_available = True
        except Exception as exc:
            logger.warning(f"Could not parse UQ calibration: {exc}")

    return MetricsResponse(
        rmse=best_training.get("rmse") if best_training else None,
        nasa_score=best_training.get("nasa_score") if best_training else None,
        ece=ece,
        coverage_90pct=coverage,
        model_version=best_training.get("run_id") if best_training else None,
        trained_at=best_training.get("trained_at") if best_training else None,
        total_training_runs=len(training_records),
        calibration_available=calibration_available,
    )


# ── GET /risk ─────────────────────────────────────────────────────────────────

@app.get("/risk", response_model=List[RiskUnitResponse])
async def get_risk():
    """
    Latest risk score and maintenance urgency for **all** engine units.

    Merges the most recent ``risk_decisions.json`` entry per unit with
    uncertainty predictions.  Units visible only in the UQ results are
    also included (risk_score defaults to 0).
    """
    results_dir = _primary_results_dir()
    risk_records = _read_json(results_dir / _RISK_FILE)
    risk_by_unit = _latest_per_unit(risk_records)

    uq_records = _read_all_uncertainty_records()
    uq_by_unit = _latest_per_unit(uq_records)

    all_unit_ids = sorted(set(risk_by_unit.keys()) | set(uq_by_unit.keys()))
    if not all_unit_ids:
        return []

    response: List[RiskUnitResponse] = []
    for uid in all_unit_ids:
        r = risk_by_unit.get(uid, {})
        uq = uq_by_unit.get(uid, {})
        rul_mean = float(r.get("rul_mean", uq.get("rul_mean", 0.0)))
        rul_std = float(r.get("rul_std", uq.get("rul_std", 0.0)))
        response.append(
            RiskUnitResponse(
                unit_id=uid,
                risk_score=float(r.get("risk_score", 0.0)),
                maintenance_urgency=r.get("maintenance_urgency", "UNKNOWN"),
                failure_probability=float(r.get("failure_prob_at_horizon", 0.0)),
                rul_mean=rul_mean,
                rul_std=rul_std,
                recommended_action=r.get("recommended_action", "No data"),
                intervention_window_cycles=int(r.get("intervention_window_cycles", 0)),
                expected_cost_eur=float(r.get("expected_cost_eur", 0.0)),
                cost_savings_vs_reactive_eur=float(
                    r.get("cost_savings_vs_reactive_eur", 0.0)
                ),
                alert_level=r.get("alert_level", "NOMINAL"),
                dataset_id=uq.get("dataset_id") or r.get("dataset_id"),
                timestamp=r.get("timestamp"),
            )
        )
    return response


# ── POST /predict ─────────────────────────────────────────────────────────────

@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """
    MC-Dropout RUL inference for a single engine unit.

    Accepts ``{unit_id, sensor_data[]}``.  ``sensor_data`` is an optional
    list of ``{name, value}`` objects.  Inference priority:

    1. Live model on **processed parquet** (best accuracy – full time history)
    2. Live model on **sensor_data payload** (single-snapshot fallback)
    3. **Stored uncertainty results** from disk (no model required)
    """
    unit_id = request.unit_id
    logger.info(f"/predict – unit_id={unit_id}")

    with _engine_lock:
        eng = _engine

    mc_samples = int(os.getenv("MC_SAMPLES", "100"))

    # 1. Live inference from parquet ──────────────────────────────────────────
    if eng is not None and eng._model is not None and eng._feature_cols:
        df_unit = _load_parquet_for_unit(unit_id)
        if df_unit is not None and not df_unit.empty:
            try:
                result = eng.predict(df_unit, mc_samples=mc_samples)
                logger.info(
                    f"/predict unit={unit_id} source=parquet "
                    f"rul_mean={result['rul_mean']:.1f} ±{result['rul_std']:.1f}"
                )
                return PredictResponse(
                    unit_id=unit_id,
                    rul_mean=round(result["rul_mean"], 3),
                    rul_std=round(result["rul_std"], 3),
                    confidence_interval=ConfidenceInterval(
                        lower=round(result["rul_lower"], 3),
                        upper=round(result["rul_upper"], 3),
                    ),
                    uncertainty_score=round(
                        result["rul_std"] / max(result["rul_mean"], 1.0), 4
                    ),
                    mc_samples=mc_samples,
                    source="model_live",
                )
            except Exception as exc:
                logger.warning(f"/predict parquet inference failed: {exc}")

    # 2. Live inference from sensor_data payload ──────────────────────────────
    if (
        eng is not None
        and eng._model is not None
        and eng._feature_cols
        and request.sensor_data
    ):
        try:
            df_payload = _sensor_data_to_df(
                unit_id, request.sensor_data, eng._feature_cols
            )
            result = eng.predict(df_payload, mc_samples=mc_samples)
            logger.info(
                f"/predict unit={unit_id} source=sensor_payload "
                f"rul_mean={result['rul_mean']:.1f} ±{result['rul_std']:.1f}"
            )
            return PredictResponse(
                unit_id=unit_id,
                rul_mean=round(result["rul_mean"], 3),
                rul_std=round(result["rul_std"], 3),
                confidence_interval=ConfidenceInterval(
                    lower=round(result["rul_lower"], 3),
                    upper=round(result["rul_upper"], 3),
                ),
                uncertainty_score=round(
                    result["rul_std"] / max(result["rul_mean"], 1.0), 4
                ),
                mc_samples=mc_samples,
                source="model_sensor_payload",
            )
        except Exception as exc:
            logger.warning(f"/predict sensor_data inference failed: {exc}")

    # 3. Stored uncertainty results ───────────────────────────────────────────
    uq_records = _read_all_uncertainty_records()
    unit_records = [
        r for r in uq_records if int(r.get("unit_id", -1)) == unit_id
    ]
    if unit_records:
        latest = unit_records[-1]
        rul_mean = float(latest.get("rul_mean", 0.0))
        rul_std = float(latest.get("rul_std", 0.0))
        ci_lower = float(
            latest.get(
                "ci_lower_90",
                latest.get("rul_lower", rul_mean - 1.645 * rul_std),
            )
        )
        ci_upper = float(
            latest.get(
                "ci_upper_90",
                latest.get("rul_upper", rul_mean + 1.645 * rul_std),
            )
        )
        logger.info(f"/predict unit={unit_id} source=stored_results")
        return PredictResponse(
            unit_id=unit_id,
            rul_mean=round(rul_mean, 3),
            rul_std=round(rul_std, 3),
            confidence_interval=ConfidenceInterval(
                lower=round(ci_lower, 3),
                upper=round(ci_upper, 3),
            ),
            uncertainty_score=round(rul_std / max(rul_mean, 1.0), 4),
            mc_samples=0,
            source="stored_results",
        )

    raise HTTPException(
        status_code=404,
        detail=(
            f"No prediction available for unit_id={unit_id}. "
            "No model artifact loaded and no stored results found. "
            "Ensure the pipeline has processed this unit."
        ),
    )


# ---------------------------------------------------------------------------
# Convenience endpoints
# ---------------------------------------------------------------------------

@app.get("/risk/{unit_id}", response_model=RiskUnitResponse)
async def get_risk_for_unit(unit_id: int):
    """Latest risk assessment for a single engine unit."""
    results_dir = _primary_results_dir()
    risk_records = _read_json(results_dir / _RISK_FILE)
    unit_records = [r for r in risk_records if int(r.get("unit_id", -1)) == unit_id]
    if not unit_records:
        raise HTTPException(
            status_code=404,
            detail=f"No risk record found for unit_id={unit_id}.",
        )
    r = unit_records[-1]
    uq_records = _read_all_uncertainty_records()
    uq_unit = next(
        (x for x in reversed(uq_records) if int(x.get("unit_id", -1)) == unit_id),
        {},
    )
    return RiskUnitResponse(
        unit_id=unit_id,
        risk_score=float(r.get("risk_score", 0.0)),
        maintenance_urgency=r.get("maintenance_urgency", "UNKNOWN"),
        failure_probability=float(r.get("failure_prob_at_horizon", 0.0)),
        rul_mean=float(r.get("rul_mean", uq_unit.get("rul_mean", 0.0))),
        rul_std=float(r.get("rul_std", uq_unit.get("rul_std", 0.0))),
        recommended_action=r.get("recommended_action", ""),
        intervention_window_cycles=int(r.get("intervention_window_cycles", 0)),
        expected_cost_eur=float(r.get("expected_cost_eur", 0.0)),
        cost_savings_vs_reactive_eur=float(
            r.get("cost_savings_vs_reactive_eur", 0.0)
        ),
        alert_level=r.get("alert_level", "NOMINAL"),
        dataset_id=uq_unit.get("dataset_id") or r.get("dataset_id"),
        timestamp=r.get("timestamp"),
    )


@app.get("/model/summary")
async def model_summary():
    """All training runs and the best model."""
    records = _read_json(_primary_results_dir() / _METRICS_FILE)
    if not records:
        return {"status": "no_model_trained_yet", "records": []}
    best = min(records, key=lambda r: r.get("rmse", float("inf")))
    return {"total_runs": len(records), "best_model": best, "all_runs": records}


@app.get("/results/latest")
async def latest_results():
    """Most recent uncertainty + risk record for every unit."""
    risk_records = _read_json(_primary_results_dir() / _RISK_FILE)
    uq_records = _read_all_uncertainty_records()

    def _fmt(records: list) -> dict:
        return {str(k): v for k, v in _latest_per_unit(records).items()}

    return {
        "uncertainty": _fmt(uq_records),
        "risk_decisions": _fmt(risk_records),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/results/history")
async def results_history(unit_id: Optional[int] = None, limit: int = 100):
    """Prediction history, optionally filtered by unit_id."""
    uq_records = _read_all_uncertainty_records()
    risk_records = _read_json(_primary_results_dir() / _RISK_FILE)
    if unit_id is not None:
        uq_records = [
            r for r in uq_records if int(r.get("unit_id", -1)) == unit_id
        ]
        risk_records = [
            r for r in risk_records if int(r.get("unit_id", -1)) == unit_id
        ]
    return {
        "uncertainty": uq_records[-limit:],
        "risk_decisions": risk_records[-limit:],
        "unit_id_filter": unit_id,
        "limit": limit,
    }



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
