"""
Probabilistic Failure Modeling Module
=======================================
Standalone component that converts RUL mean + std (from the
UncertaintyQuantification output) into actionable failure-probability
metrics, hazard rates and survival curves, with an optional Weibull fit.

Architecture (§4.6 ARCHITECTURE.md)
-------------------------------------
Input
    Reads ``data/metrics_and_results/uncertainty_*.json`` files written by
    UncertaintyQuantification.  Also triggered by MQTT messages on
    ``cmapss/uncertainty`` carrying a ``dataset_id`` payload.

Processing (per engine unit)
    1. ``P(failure ≤ N cycles)`` via normal CDF on the RUL posterior:
           P(T ≤ N) = Φ((N − μ) / σ)
       evaluated at N ∈ {10, 20, 30, 50} cycles.
    2. ``Hazard rate h(t)`` = φ(z) / (σ · S(t))  at each evaluation horizon.
    3. ``Survival curve S(t)`` = 1 − Φ((t − μ) / σ)  at multiple horizons.
    4. Optional Weibull fit via ``scipy.stats.weibull_min`` on reconstructed
       MC samples (synthetic, derived from the normal posterior).

Output
    Persists per-unit results to
    ``data/metrics_and_results/failure_prob_{unit_id}.json``.
    Publishes a summary payload to MQTT topic ``cmapss/risk``.

MQTT
    Subscribe : ``cmapss/uncertainty``
    Publish   : ``cmapss/risk``

Component base
    ``PipelineComponent`` from ``src.common.components``.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from configs import config
from src.common.components import PipelineComponent

# ---------------------------------------------------------------------------
# Optional scipy (graceful degradation for Weibull fit)
# ---------------------------------------------------------------------------
_weibull_min = None  # type: ignore[assignment]
np = None            # type: ignore[assignment]
SCIPY_AVAILABLE = False

try:
    from scipy.stats import weibull_min as _weibull_min  # type: ignore[assignment]
    import numpy as np                                    # type: ignore[assignment]
    SCIPY_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning(
        "scipy/numpy not available – Weibull fitting disabled."
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAILURE_HORIZONS: List[int] = [10, 20, 30, 50]   # cycles
SURVIVAL_HORIZONS: List[int] = [10, 20, 30, 50, 70, 100, 125]  # cycles
MC_SYNTHETIC_SAMPLES: int = 500   # synthetic samples for Weibull fit

SUBSCRIBE_TOPIC: str = config.MQTT["TOPICS"]["UNCERTAINTY"]
PUBLISH_TOPIC: str = config.MQTT["TOPICS"]["RISK"]

# Output directory (primary = data/metrics_and_results, fallback = data/results)
_OUTPUT_DIR_PRIMARY: str = config.DATA.get("METRICS_AND_RESULTS", "data/metrics_and_results")
_OUTPUT_DIR_FALLBACK: str = config.DATA["RESULTS"]

# Input: where UQ writes uncertainty_{dataset_id}.json files
_UQ_INPUT_CANDIDATES: List[str] = [
    config.DATA.get("METRICS_AND_RESULTS", "data/metrics_and_results"),
    config.DATA["RESULTS"],
]

logger = logging.getLogger(__name__)


# ===========================================================================
# Pure mathematical helpers
# ===========================================================================

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erfc (no scipy dependency)."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def failure_probability(rul_mean: float, rul_std: float, horizon: int) -> float:
    """
    P(T ≤ horizon) under N(rul_mean, rul_std²) RUL distribution.

    Parameters
    ----------
    rul_mean  : posterior mean RUL (cycles)
    rul_std   : posterior standard deviation
    horizon   : evaluation horizon (cycles)

    Returns
    -------
    float in [0, 1]
    """
    sigma = max(rul_std, 1e-6)
    z = (horizon - rul_mean) / sigma
    return round(_norm_cdf(z), 6)


def survival_probability(rul_mean: float, rul_std: float, t: int) -> float:
    """S(t) = 1 − P(T ≤ t)."""
    return round(1.0 - failure_probability(rul_mean, rul_std, t), 6)


def hazard_rate(rul_mean: float, rul_std: float, t: int) -> float:
    """
    Instantaneous hazard rate h(t) = f(t) / S(t).

    Uses the normal distribution assumption:
        f(t) = φ((t − μ) / σ) / σ
        S(t) = 1 − Φ((t − μ) / σ)
    """
    sigma = max(rul_std, 1e-6)
    z = (t - rul_mean) / sigma
    pdf_val = _norm_pdf(z) / sigma
    surv = max(survival_probability(rul_mean, rul_std, t), 1e-9)
    return round(pdf_val / surv, 8)


def build_failure_probs(
    rul_mean: float,
    rul_std: float,
    horizons: Optional[List[int]] = None,
) -> Dict[str, float]:
    """Return {str(N): P(failure ≤ N)} for all requested horizons."""
    if horizons is None:
        horizons = FAILURE_HORIZONS
    return {
        str(n): failure_probability(rul_mean, rul_std, n)
        for n in horizons
    }


def build_survival_curve(
    rul_mean: float,
    rul_std: float,
    horizons: Optional[List[int]] = None,
) -> Dict[str, float]:
    """Return {str(t): S(t)} for all requested horizons."""
    if horizons is None:
        horizons = SURVIVAL_HORIZONS
    return {
        str(t): survival_probability(rul_mean, rul_std, t)
        for t in horizons
    }


def build_hazard_curve(
    rul_mean: float,
    rul_std: float,
    horizons: Optional[List[int]] = None,
) -> Dict[str, float]:
    """Return {str(t): h(t)} for all requested horizons."""
    if horizons is None:
        horizons = SURVIVAL_HORIZONS
    return {
        str(t): hazard_rate(rul_mean, rul_std, t)
        for t in horizons
    }


def alert_level(rul_mean: float, p_failure_30: float) -> str:
    """Derive alert level from RUL mean and failure probability at 30 cycles."""
    if rul_mean <= 20 or p_failure_30 >= 0.70:
        return "CRITICAL"
    elif rul_mean <= 50 or p_failure_30 >= 0.30:
        return "WARNING"
    return "NOMINAL"


# ===========================================================================
# Optional Weibull fit
# ===========================================================================

def fit_weibull(
    rul_mean: float,
    rul_std: float,
    n_samples: int = MC_SYNTHETIC_SAMPLES,
) -> Optional[Dict]:
    """
    Fit a Weibull (3-parameter via ``scipy.stats.weibull_min``) distribution
    to synthetic RUL samples drawn from N(rul_mean, rul_std²).

    Parameters
    ----------
    rul_mean  : posterior mean RUL
    rul_std   : posterior std
    n_samples : number of synthetic samples (default 500)

    Returns
    -------
    dict with keys: shape (c), loc, scale, aic, bic  — or None if scipy
    is unavailable or the fit fails.
    """
    if not SCIPY_AVAILABLE or _weibull_min is None or np is None:
        return None

    rng = np.random.default_rng(seed=42)
    samples = rng.normal(loc=rul_mean, scale=max(rul_std, 1e-3), size=n_samples)
    # Weibull requires positive support; clip to 1
    samples = np.clip(samples, 1.0, None)

    try:
        c, loc, scale = _weibull_min.fit(samples, floc=0)
        # AIC / BIC (2 free params: c and scale, since loc is fixed to 0)
        log_lik = float(np.sum(_weibull_min.logpdf(samples, c, loc=loc, scale=scale)))
        k = 2
        n = len(samples)
        aic = round(2 * k - 2 * log_lik, 4)
        bic = round(k * math.log(n) - 2 * log_lik, 4)
        return {
            "shape_c": round(float(c), 6),
            "loc": round(float(loc), 6),
            "scale": round(float(scale), 6),
            "log_likelihood": round(log_lik, 4),
            "aic": aic,
            "bic": bic,
            "n_samples_used": n_samples,
        }
    except Exception as exc:
        logger.warning(f"Weibull fit failed: {exc}")
        return None


# ===========================================================================
# Per-unit computation
# ===========================================================================

def compute_unit_failure_profile(
    unit_id: int,
    rul_mean: float,
    rul_std: float,
    dataset_id: str = "",
    fit_weibull_flag: bool = True,
) -> dict:
    """
    Full failure profile for a single engine unit.

    Returns
    -------
    dict with:
        unit_id, dataset_id, rul_mean, rul_std,
        failure_probabilities  : {str(N): P(failure ≤ N)}  for N in FAILURE_HORIZONS
        survival_curve         : {str(t): S(t)}
        hazard_curve           : {str(t): h(t)}
        alert_level            : NOMINAL / WARNING / CRITICAL
        weibull_fit            : dict or None
        computed_at            : ISO-8601 timestamp
    """
    f_probs = build_failure_probs(rul_mean, rul_std)
    surv = build_survival_curve(rul_mean, rul_std)
    haz = build_hazard_curve(rul_mean, rul_std)
    level = alert_level(rul_mean, f_probs.get("30", 0.0))

    weibull: Optional[dict] = None
    if fit_weibull_flag:
        weibull = fit_weibull(rul_mean, rul_std)

    return {
        "unit_id": unit_id,
        "dataset_id": dataset_id,
        "rul_mean": round(rul_mean, 3),
        "rul_std": round(rul_std, 3),
        "failure_probabilities": f_probs,
        "survival_curve": surv,
        "hazard_curve": haz,
        "alert_level": level,
        "weibull_fit": weibull,
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ===========================================================================
# I/O helpers
# ===========================================================================

def _resolve_output_dir() -> Path:
    primary = Path(_OUTPUT_DIR_PRIMARY)
    primary.mkdir(parents=True, exist_ok=True)
    return primary


def _find_uq_files() -> List[Path]:
    """Search all candidate directories for uncertainty_*.json files."""
    found: List[Path] = []
    for candidate in _UQ_INPUT_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            found.extend(sorted(p.glob("uncertainty_*.json")))
    # De-duplicate by filename (prefer first candidate)
    seen_names: set = set()
    unique: List[Path] = []
    for fp in found:
        if fp.name not in seen_names:
            seen_names.add(fp.name)
            unique.append(fp)
    return unique


def _load_uq_for_dataset(dataset_id: str) -> Optional[dict]:
    """Load the UQ document for a given dataset_id."""
    for candidate in _UQ_INPUT_CANDIDATES:
        path = Path(candidate) / f"uncertainty_{dataset_id}.json"
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning(f"Could not read {path}: {exc}")
    return None


def persist_unit_profile(profile: dict, output_dir: Path) -> Path:
    """Save failure profile to failure_prob_{unit_id}.json."""
    out_path = output_dir / f"failure_prob_{profile['unit_id']}.json"
    with open(out_path, "w") as fh:
        json.dump(profile, fh, indent=2)
    return out_path


# ===========================================================================
# PipelineComponent
# ===========================================================================

class ProbabilisticFailureModeling(PipelineComponent):
    """
    Converts RUL posterior (mean + std) into failure probabilities,
    hazard rates, survival curves and an optional Weibull fit.

    Subscribes to  : ``cmapss/uncertainty``
    Publishes to   : ``cmapss/risk``
    Input files    : ``data/metrics_and_results/uncertainty_{dataset_id}.json``
    Output files   : ``data/metrics_and_results/failure_prob_{unit_id}.json``
    """

    def __init__(
        self,
        fit_weibull: bool = True,
        output_dir: Optional[str] = None,
    ):
        super().__init__(
            name="ProbabilisticFailureModeling",
            mqtt_topic_subscribe_list=[SUBSCRIBE_TOPIC],
        )
        self._fit_weibull: bool = bool(
            os.getenv("FIT_WEIBULL", str(fit_weibull)).lower() in ("1", "true", "yes")
        )
        self._output_dir: Path = Path(output_dir or _OUTPUT_DIR_PRIMARY)
        self._queue: List[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        super().setup()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(
            f"{self.name}: ready  "
            f"subscribe={SUBSCRIBE_TOPIC}  publish={PUBLISH_TOPIC}  "
            f"weibull={'on' if self._fit_weibull else 'off'}"
        )

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown complete")

    # ------------------------------------------------------------------
    # MQTT callback
    # ------------------------------------------------------------------

    def on_message_received(self, payload: dict) -> None:
        """
        Accept any message that carries a ``dataset_id``.
        Supported types: ``UQ_RESULT``, ``UQ_REQUEST``, or bare payload with
        ``dataset_id``.
        """
        dataset_id = payload.get("dataset_id")
        if not dataset_id:
            self.logger.warning(
                f"{self.name}: message without dataset_id – skipped"
            )
            return
        self.logger.info(
            f"{self.name}: queued failure-modeling request for dataset_id={dataset_id}"
        )
        self._queue.append(payload)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def execute(self) -> None:
        while self._queue:
            item = self._queue.pop(0)
            dataset_id = item.get("dataset_id")
            try:
                self._process_dataset(dataset_id, item)
            except Exception as exc:
                self.logger.exception(
                    f"{self.name}: error processing dataset_id={dataset_id}: {exc}"
                )

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def _process_dataset(self, dataset_id: str, trigger: dict) -> None:
        """Full failure-modeling pipeline for one dataset_id."""
        self.logger.info(
            f"{self.name}: processing failure profile for dataset_id={dataset_id}"
        )

        # 1. Load UQ results (prefer inline payload unit_predictions, then file)
        unit_predictions = trigger.get("unit_predictions")
        if not unit_predictions:
            uq_doc = _load_uq_for_dataset(dataset_id)
            if uq_doc is None:
                self.logger.error(
                    f"{self.name}: no UQ data found for dataset_id={dataset_id}"
                )
                return
            unit_predictions = uq_doc.get("unit_predictions", [])

        if not unit_predictions:
            self.logger.warning(
                f"{self.name}: empty unit_predictions for dataset_id={dataset_id}"
            )
            return

        # 2. Compute failure profile per unit
        profiles: List[dict] = []
        for pred in unit_predictions:
            unit_id = pred.get("unit_id")
            rul_mean = float(pred.get("rul_mean", 0.0))
            rul_std = float(pred.get("rul_std", 1.0))

            profile = compute_unit_failure_profile(
                unit_id=int(unit_id),
                rul_mean=rul_mean,
                rul_std=rul_std,
                dataset_id=dataset_id,
                fit_weibull_flag=self._fit_weibull,
            )
            profiles.append(profile)

            # Persist individual file
            out_path = persist_unit_profile(profile, self._output_dir)
            self.logger.info(
                f"{self.name}: unit={unit_id}  "
                f"alert={profile['alert_level']}  "
                f"P(fail≤30)={profile['failure_probabilities'].get('30', 'n/a')}  "
                f"→ {out_path.name}"
            )

        # 3. Publish summary to cmapss/risk
        n_critical = sum(1 for p in profiles if p["alert_level"] == "CRITICAL")
        n_warning = sum(1 for p in profiles if p["alert_level"] == "WARNING")

        publish_payload = {
            "type": "FAILURE_PROFILES",
            "dataset_id": dataset_id,
            "n_units": len(profiles),
            "n_critical": n_critical,
            "n_warning": n_warning,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "profiles": profiles,
        }
        self.send_message(PUBLISH_TOPIC, publish_payload)
        self.logger.info(
            f"{self.name}: published {len(profiles)} failure profiles "
            f"for {dataset_id}  "
            f"(CRITICAL={n_critical}, WARNING={n_warning}) → {PUBLISH_TOPIC}"
        )

    # ------------------------------------------------------------------
    # Batch: scan all existing UQ files at startup
    # ------------------------------------------------------------------

    def scan_and_process_existing(self) -> None:
        """
        At startup, scan all existing uncertainty_*.json files and compute
        failure profiles for any that don't already have a matching
        failure_prob_{unit_id}.json.
        """
        uq_files = _find_uq_files()
        if not uq_files:
            self.logger.info(
                f"{self.name}: no existing UQ files found – waiting for MQTT triggers"
            )
            return

        self.logger.info(
            f"{self.name}: found {len(uq_files)} UQ file(s) – processing…"
        )
        for uq_file in uq_files:
            # Derive dataset_id from filename: uncertainty_{dataset_id}.json
            stem = uq_file.stem  # e.g. "uncertainty_test_FD001"
            dataset_id = stem.replace("uncertainty_", "", 1)
            try:
                with open(uq_file) as f:
                    uq_doc = json.load(f)
                unit_preds = uq_doc.get("unit_predictions", [])
                if not unit_preds:
                    continue
                self._process_dataset(dataset_id, {"dataset_id": dataset_id,
                                                    "unit_predictions": unit_preds})
            except Exception as exc:
                self.logger.warning(
                    f"{self.name}: skipping {uq_file.name} – {exc}"
                )


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("\n" + "=" * 65)
    print("📉 [PROBABILISTIC FAILURE MODELING CONTAINER ONLINE]")
    print(f"   Subscribe : {SUBSCRIBE_TOPIC}")
    print(f"   Publish   : {PUBLISH_TOPIC}")
    print(f"   Horizons  : {FAILURE_HORIZONS} cycles")
    print(f"   Output    : {_OUTPUT_DIR_PRIMARY}")
    print("=" * 65 + "\n")

    component = ProbabilisticFailureModeling()
    component.setup()

    # Process any UQ files already on disk before entering MQTT loop
    component.scan_and_process_existing()

    try:
        while True:
            component.execute()
            time.sleep(0.5)
    except KeyboardInterrupt:
        component.teardown()
        logging.getLogger(__name__).info(
            "🛑 ProbabilisticFailureModeling stopped"
        )

