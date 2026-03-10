"""
Risk Decision Engine
=====================
Standalone component that transforms failure-probability profiles into
actionable risk assessments and maintenance decisions.

Architecture (§4.7 ARCHITECTURE.md)
-------------------------------------
Inputs  (MQTT ``cmapss/risk``, type ``FAILURE_PROFILES`` from ProbabilisticFailureModeling):
    unit_id, rul_mean, rul_std,
    failure_probabilities  {str(N): P(failure ≤ N)},
    survival_curve, hazard_curve, alert_level, weibull_fit

Processing (per unit)
    1. Risk score  = P(failure ≤ threshold_cycles) × severity_weight
       where threshold_cycles and severity_weight are configurable.
    2. Urgency classification: CRITICAL / HIGH / MEDIUM / LOW
       driven by risk_score relative to RISK_THRESHOLD (env var, default 0.7).
    3. Intervention window: next N cycles range [lower, upper].
    4. Detailed recommended action string.

Outputs
    • Persists ``data/metrics_and_results/risk_assessment_{unit_id}.json``
    • Publishes summary to ``cmapss/economic``

Environment variables (all optional, have defaults)
    RISK_THRESHOLD      float [0,1]   overall risk tolerance (default 0.7)
    SEVERITY_WEIGHT     float >0      multiplier on failure probability (default 1.0)
    HORIZON_CYCLES      int           failure-prob horizon used for risk score (default 30)

MQTT
    Subscribe : ``cmapss/risk``
    Publish   : ``cmapss/economic``

Component base
    ``PipelineComponent`` from ``src.common.components``
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from configs import config
from src.common.components import PipelineComponent

# ---------------------------------------------------------------------------
# Topic constants
# ---------------------------------------------------------------------------
SUBSCRIBE_TOPIC: str = config.MQTT["TOPICS"]["RISK"]
PUBLISH_TOPIC: str = config.MQTT["TOPICS"]["ECONOMIC"]

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
_OUTPUT_DIR: str = config.DATA.get("METRICS_AND_RESULTS", "data/metrics_and_results")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Urgency band thresholds  (relative to RISK_THRESHOLD)
#
#   CRITICAL  : risk_score ≥ RISK_THRESHOLD
#   HIGH      : risk_score ≥ RISK_THRESHOLD * 0.57   (≈ 0.40 with default 0.7)
#   MEDIUM    : risk_score ≥ RISK_THRESHOLD * 0.29   (≈ 0.20 with default 0.7)
#   LOW       : otherwise
# ---------------------------------------------------------------------------
_URGENCY_FRACTIONS: List[Tuple[str, float]] = [
    ("CRITICAL", 1.00),
    ("HIGH",     0.57),
    ("MEDIUM",   0.29),
    ("LOW",      0.00),
]

# Intervention window multipliers per urgency
_WINDOW_FRACTIONS: Dict[str, Tuple[float, float]] = {
    "CRITICAL": (0.10, 0.25),   # act within 10–25 % of estimated RUL
    "HIGH":     (0.25, 0.50),
    "MEDIUM":   (0.50, 0.75),
    "LOW":      (0.75, 1.00),
}

_MIN_WINDOW: Dict[str, int] = {
    "CRITICAL": 1,
    "HIGH":     5,
    "MEDIUM":  10,
    "LOW":     20,
}


# ===========================================================================
# Pure computation helpers
# ===========================================================================

def compute_risk_score(
    failure_prob: float,
    rul_std: float,
    rul_mean: float,
    severity_weight: float,
    hazard_at_horizon: float = 0.0,
) -> float:
    """
    Composite risk score ∈ [0, 1].

    risk_score = clip(
        severity_weight × (0.60 × P_failure
                         + 0.25 × hazard_norm
                         + 0.15 × uncertainty_norm),
        0, 1
    )

    Parameters
    ----------
    failure_prob      : P(failure ≤ horizon)
    rul_std           : posterior std of RUL
    rul_mean          : posterior mean of RUL
    severity_weight   : configurable multiplier (env SEVERITY_WEIGHT, default 1.0)
    hazard_at_horizon : h(horizon) from hazard_curve (optional, default 0)
    """
    hazard_norm = min(hazard_at_horizon / 0.5, 1.0)
    uncertainty_norm = min(rul_std / max(rul_mean, 1.0), 1.0)

    raw = (
        0.60 * failure_prob
        + 0.25 * hazard_norm
        + 0.15 * uncertainty_norm
    ) * severity_weight

    return round(min(max(raw, 0.0), 1.0), 6)


def classify_urgency(risk_score: float, risk_threshold: float) -> str:
    """
    Map risk_score to urgency label using thresholds relative to
    ``risk_threshold``.

    CRITICAL : risk_score ≥ risk_threshold
    HIGH     : risk_score ≥ risk_threshold × 0.57
    MEDIUM   : risk_score ≥ risk_threshold × 0.29
    LOW      : otherwise
    """
    for label, fraction in _URGENCY_FRACTIONS:
        if risk_score >= risk_threshold * fraction:
            return label
    return "LOW"


def compute_intervention_window(
    rul_mean: float,
    urgency: str,
) -> Tuple[int, int]:
    """
    Return (lower_bound, upper_bound) intervention window in cycles.

    Uses RUL mean scaled by urgency-specific fractions.
    """
    lo_frac, hi_frac = _WINDOW_FRACTIONS.get(urgency, (0.75, 1.00))
    min_cycles = _MIN_WINDOW.get(urgency, 1)
    lower = max(min_cycles, int(rul_mean * lo_frac))
    upper = max(lower + 1, int(rul_mean * hi_frac))
    return lower, upper


def build_recommended_action(
    urgency: str,
    rul_mean: float,
    window_lower: int,
    window_upper: int,
    risk_score: float,
) -> str:
    """Human-readable maintenance recommendation."""
    templates = {
        "CRITICAL": (
            f"⛔ IMMEDIATE ACTION REQUIRED — risk score {risk_score:.3f}. "
            f"Estimated RUL {rul_mean:.0f} cycles. "
            f"Schedule maintenance within {window_lower}–{window_upper} cycle(s)."
        ),
        "HIGH": (
            f"🔴 HIGH RISK (score {risk_score:.3f}) — "
            f"schedule maintenance within {window_lower}–{window_upper} cycles. "
            f"Estimated RUL {rul_mean:.0f} cycles."
        ),
        "MEDIUM": (
            f"🟡 ELEVATED RISK (score {risk_score:.3f}) — "
            f"plan maintenance within {window_lower}–{window_upper} cycles. "
            f"Estimated RUL {rul_mean:.0f} cycles. Monitor closely."
        ),
        "LOW": (
            f"🟢 NOMINAL (score {risk_score:.3f}) — "
            f"next inspection within {window_lower}–{window_upper} cycles. "
            f"Estimated RUL {rul_mean:.0f} cycles."
        ),
    }
    return templates.get(urgency, "No recommendation available.")


def process_unit_profile(
    profile: dict,
    risk_threshold: float,
    severity_weight: float,
    horizon_cycles: int,
) -> dict:
    """
    Compute a full risk assessment for a single engine unit profile.

    Parameters
    ----------
    profile         : per-unit dict from ProbabilisticFailureModeling
    risk_threshold  : env RISK_THRESHOLD (default 0.7)
    severity_weight : env SEVERITY_WEIGHT (default 1.0)
    horizon_cycles  : env HORIZON_CYCLES (default 30)

    Returns
    -------
    dict  – complete risk assessment record
    """
    unit_id = int(profile.get("unit_id", 0))
    rul_mean = float(profile.get("rul_mean", 0.0))
    rul_std = float(profile.get("rul_std", 1.0))
    dataset_id = profile.get("dataset_id", "")

    # Failure probability at the configured horizon
    f_probs: Dict[str, float] = profile.get("failure_probabilities", {})
    failure_prob = float(
        f_probs.get(str(horizon_cycles))
        or f_probs.get(str(min(int(k) for k in f_probs.keys()) if f_probs else 30))
        or 0.0
    )

    # Hazard rate at horizon (optional, graceful fallback)
    hazard_curve: Dict[str, float] = profile.get("hazard_curve", {})
    hazard_at_horizon = float(
        hazard_curve.get(str(horizon_cycles), 0.0)
    )

    # Survival at horizon
    survival_curve: Dict[str, float] = profile.get("survival_curve", {})
    survival_at_horizon = float(
        survival_curve.get(str(horizon_cycles), 1.0 - failure_prob)
    )

    # Core computations
    risk_score = compute_risk_score(
        failure_prob, rul_std, rul_mean, severity_weight, hazard_at_horizon
    )
    urgency = classify_urgency(risk_score, risk_threshold)
    win_lower, win_upper = compute_intervention_window(rul_mean, urgency)
    action = build_recommended_action(urgency, rul_mean, win_lower, win_upper, risk_score)

    return {
        "type": "RISK_ASSESSMENT",
        "unit_id": unit_id,
        "dataset_id": dataset_id,
        # Input summary
        "rul_mean": round(rul_mean, 3),
        "rul_std": round(rul_std, 3),
        "failure_prob_at_horizon": round(failure_prob, 6),
        "horizon_cycles": horizon_cycles,
        "hazard_at_horizon": round(hazard_at_horizon, 8),
        "survival_at_horizon": round(survival_at_horizon, 6),
        # Risk outputs
        "risk_score": risk_score,
        "risk_threshold": round(risk_threshold, 4),
        "severity_weight": round(severity_weight, 4),
        "maintenance_urgency": urgency,
        "intervention_window_lower": win_lower,
        "intervention_window_upper": win_upper,
        "recommended_action": action,
        # Pass-through curves for downstream consumers
        "failure_probabilities": f_probs,
        "survival_curve": survival_curve,
        "hazard_curve": hazard_curve,
        "weibull_fit": profile.get("weibull_fit"),
        "alert_level": profile.get("alert_level", urgency),
        "assessed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ===========================================================================
# PipelineComponent
# ===========================================================================

class RiskDecisionEngine(PipelineComponent):
    """
    Risk-Aware Decision Engine (§4.7 ARCHITECTURE.md).

    Subscribes to  ``cmapss/risk``     (FAILURE_PROFILES from ProbabilisticFailureModeling)
    Publishes to   ``cmapss/economic`` (RISK_ASSESSMENT batch)

    Per-unit output: ``data/metrics_and_results/risk_assessment_{unit_id}.json``

    Configurable via environment variables
    --------------------------------------
    RISK_THRESHOLD   float [0,1]   default 0.7
    SEVERITY_WEIGHT  float >0      default 1.0
    HORIZON_CYCLES   int           default 30
    """

    def __init__(
        self,
        risk_threshold: float = 0.7,
        severity_weight: float = 1.0,
        horizon_cycles: int = 30,
        output_dir: Optional[str] = None,
    ):
        super().__init__(
            name="RiskDecisionEngine",
            mqtt_topic_subscribe_list=[SUBSCRIBE_TOPIC],
        )
        self._risk_threshold: float = float(
            os.getenv("RISK_THRESHOLD", str(risk_threshold))
        )
        self._severity_weight: float = float(
            os.getenv("SEVERITY_WEIGHT", str(severity_weight))
        )
        self._horizon_cycles: int = int(
            os.getenv("HORIZON_CYCLES", str(horizon_cycles))
        )
        self._output_dir: Path = Path(output_dir or _OUTPUT_DIR)
        self._queue: List[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        super().setup()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(
            f"{self.name}: ready — "
            f"RISK_THRESHOLD={self._risk_threshold}  "
            f"SEVERITY_WEIGHT={self._severity_weight}  "
            f"HORIZON_CYCLES={self._horizon_cycles}  "
            f"subscribe={SUBSCRIBE_TOPIC}  publish={PUBLISH_TOPIC}"
        )

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown complete")

    # ------------------------------------------------------------------
    # MQTT callback
    # ------------------------------------------------------------------

    def on_message_received(self, payload: dict) -> None:
        """
        Accept ``FAILURE_PROFILES`` batch messages (from ProbabilisticFailureModeling)
        and single-unit ``FAILURE_PROFILE`` messages.
        Any payload carrying ``profiles`` or ``unit_id`` is accepted.
        """
        msg_type = payload.get("type", "")
        has_profiles = "profiles" in payload
        has_unit = "unit_id" in payload or "rul_mean" in payload

        if has_profiles or has_unit or msg_type in (
            "FAILURE_PROFILES", "FAILURE_PROFILE", "UQ_RESULT"
        ):
            dataset_id = payload.get("dataset_id", "unknown")
            self.logger.info(
                f"{self.name}: queued risk-decision request "
                f"type={msg_type!r}  dataset_id={dataset_id}"
            )
            self._queue.append(payload)
        else:
            self.logger.debug(
                f"{self.name}: ignored message type={msg_type!r}"
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def execute(self) -> None:
        while self._queue:
            item = self._queue.pop(0)
            try:
                self._process_message(item)
            except Exception as exc:
                self.logger.exception(
                    f"{self.name}: error processing message: {exc}"
                )

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def _process_message(self, payload: dict) -> None:
        """
        Dispatch a single queued message.
        Handles both batch (``profiles`` key) and single-unit payloads.
        """
        profiles_raw: List[dict] = payload.get("profiles", [])

        # Single-unit message: treat the payload itself as one profile
        if not profiles_raw and "unit_id" in payload:
            profiles_raw = [payload]

        if not profiles_raw:
            self.logger.warning(f"{self.name}: no unit profiles found in message")
            return

        dataset_id = payload.get("dataset_id", "")
        assessments: List[dict] = []

        for profile in profiles_raw:
            try:
                assessment = process_unit_profile(
                    profile,
                    self._risk_threshold,
                    self._severity_weight,
                    self._horizon_cycles,
                )
                assessments.append(assessment)
                self._persist_unit(assessment)
                self._log_assessment(assessment)
            except Exception as exc:
                uid = profile.get("unit_id", "?")
                self.logger.warning(
                    f"{self.name}: failed to assess unit_id={uid}: {exc}"
                )

        if not assessments:
            return

        # Aggregate counts for the publish payload
        n_critical = sum(1 for a in assessments if a["maintenance_urgency"] == "CRITICAL")
        n_high = sum(1 for a in assessments if a["maintenance_urgency"] == "HIGH")
        n_medium = sum(1 for a in assessments if a["maintenance_urgency"] == "MEDIUM")
        n_low = sum(1 for a in assessments if a["maintenance_urgency"] == "LOW")

        publish_payload = {
            "type": "RISK_ASSESSMENTS",
            "dataset_id": dataset_id,
            "n_units": len(assessments),
            "n_critical": n_critical,
            "n_high": n_high,
            "n_medium": n_medium,
            "n_low": n_low,
            "risk_threshold": self._risk_threshold,
            "severity_weight": self._severity_weight,
            "horizon_cycles": self._horizon_cycles,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "assessments": assessments,
        }

        self.send_message(PUBLISH_TOPIC, publish_payload)
        self.logger.info(
            f"{self.name}: published {len(assessments)} risk assessments "
            f"for dataset_id={dataset_id!r} → {PUBLISH_TOPIC}  "
            f"(CRITICAL={n_critical} HIGH={n_high} MEDIUM={n_medium} LOW={n_low})"
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_unit(self, assessment: dict) -> None:
        """
        Write ``data/metrics_and_results/risk_assessment_{unit_id}.json``.

        Each file stores the **full history** of assessments for that unit
        (capped at 10 000 records to prevent unbounded growth).
        """
        unit_id = assessment["unit_id"]
        path = self._output_dir / f"risk_assessment_{unit_id}.json"

        existing: list = []
        if path.exists():
            try:
                with open(path) as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
            except Exception:
                existing = []

        existing.append(assessment)
        existing = existing[-10_000:]

        with open(path, "w") as f:
            json.dump(existing, f, indent=2)

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_assessment(self, assessment: dict) -> None:
        uid = assessment["unit_id"]
        score = assessment["risk_score"]
        urgency = assessment["maintenance_urgency"]
        rul = assessment["rul_mean"]
        prob = assessment["failure_prob_at_horizon"]
        win_lo = assessment["intervention_window_lower"]
        win_hi = assessment["intervention_window_upper"]

        self.logger.info(
            f"{self.name}: unit={uid}  score={score:.3f}  urgency={urgency}  "
            f"RUL={rul:.1f}  P(fail≤{assessment['horizon_cycles']})={prob:.3f}  "
            f"window=[{win_lo},{win_hi}]"
        )
        if urgency in ("CRITICAL", "HIGH"):
            self.logger.warning(
                f"{self.name}: ⚠️  {urgency} alert — unit {uid}  "
                f"risk_score={score:.3f}  threshold={self._risk_threshold}"
            )


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    _rt = float(os.getenv("RISK_THRESHOLD", "0.7"))
    _sw = float(os.getenv("SEVERITY_WEIGHT", "1.0"))
    _hc = int(os.getenv("HORIZON_CYCLES", "30"))

    print("\n" + "=" * 65)
    print("⚠️  [RISK DECISION ENGINE CONTAINER ONLINE]")
    print(f"   Subscribe     : {SUBSCRIBE_TOPIC}")
    print(f"   Publish       : {PUBLISH_TOPIC}")
    print(f"   RISK_THRESHOLD: {_rt}")
    print(f"   SEVERITY_WEIGHT: {_sw}")
    print(f"   HORIZON_CYCLES : {_hc}")
    print("=" * 65 + "\n")

    component = RiskDecisionEngine(
        risk_threshold=_rt,
        severity_weight=_sw,
        horizon_cycles=_hc,
    )
    component.setup()

    try:
        while True:
            component.execute()
            time.sleep(0.5)
    except KeyboardInterrupt:
        component.teardown()
        logging.getLogger(__name__).info("🛑 RiskDecisionEngine stopped")

