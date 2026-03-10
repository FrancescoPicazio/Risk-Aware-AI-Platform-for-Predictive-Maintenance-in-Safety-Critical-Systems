"""
Risk & Cost Engine
==================
Core decision module that transforms uncertainty-enriched failure metrics into
actionable maintenance decisions and economic optimisation outputs.

Architecture
------------
Inputs  (MQTT topic cmapss/uncertainty_failure, type=FAILURE_METRICS):
    - unit_id, rul_mean, rul_std, failure_prob_at_horizon, hazard_rate, alert_level

Outputs (MQTT topic cmapss/risk_cost, type=RISK_DECISION):
    - risk_score            : 0-1 composite risk index
    - maintenance_urgency   : CRITICAL / HIGH / MEDIUM / LOW
    - recommended_action    : human-readable text
    - intervention_window   : recommended action window (cycles)
    - expected_cost         : E[Cost] = P_late * C_late + P_early * C_early
    - cost_savings_vs_reactive : estimated savings vs. always-reactive strategy

Economic model
--------------
E[Cost] = P(late) * C_late + P(early) * C_early

where:
    P(late)  = failure probability if we wait (= failure_prob_at_horizon)
    P(early) = 1 - P(late)
    C_late   = cost of unplanned failure (default: 50 000 €)
    C_early  = cost of preventive maintenance (default: 5 000 €)

The optimal intervention threshold θ* minimises E[Cost] and is:
    θ* = C_early / (C_late + C_early)
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from configs import config

# ---------------------------------------------------------------------------
# Default cost parameters (can be overridden via env variables or config)
# ---------------------------------------------------------------------------
C_LATE: float = 50_000.0    # € cost of an unplanned failure / late maintenance
C_EARLY: float = 5_000.0    # € cost of planned / preventive maintenance

# Optimal probability threshold: θ* = C_early / (C_late + C_early)
OPTIMAL_THRESHOLD: float = C_EARLY / (C_LATE + C_EARLY)

# Risk tolerance override per urgency band
URGENCY_BANDS = {
    "CRITICAL": (0.7, float("inf")),   # risk_score ≥ 0.7
    "HIGH":     (0.4, 0.7),
    "MEDIUM":   (0.2, 0.4),
    "LOW":      (0.0, 0.2),
}

RESULTS_DIR: str = config.DATA["RESULTS"]


# ---------------------------------------------------------------------------
# Pure functions – stateless, easily testable
# ---------------------------------------------------------------------------

def compute_risk_score(
    failure_prob: float,
    hazard_rate: float,
    rul_mean: float,
    rul_std: float,
) -> float:
    """
    Composite risk score ∈ [0, 1].

    Combines:
    - Failure probability          (weight 0.50)
    - Normalised hazard rate       (weight 0.30)
    - Relative uncertainty penalty (weight 0.20)
    """
    # Normalise hazard rate: map [0, 0.5] → [0, 1] with saturation
    hazard_norm = min(hazard_rate / 0.5, 1.0)

    # Relative uncertainty: std / max(mean, 1)
    uncertainty_norm = min(rul_std / max(rul_mean, 1.0), 1.0)

    score = (
        0.50 * failure_prob
        + 0.30 * hazard_norm
        + 0.20 * uncertainty_norm
    )
    return round(min(score, 1.0), 6)


def compute_urgency(risk_score: float) -> str:
    """Map risk score to maintenance urgency label."""
    for label, (low, high) in URGENCY_BANDS.items():
        if low <= risk_score < high:
            return label
    return "LOW"


def compute_intervention_window(rul_mean: float, urgency: str) -> int:
    """
    Recommended intervention window in cycles.
    Returns conservative (early) window based on urgency.
    """
    if urgency == "CRITICAL":
        return max(1, int(rul_mean * 0.25))
    elif urgency == "HIGH":
        return max(5, int(rul_mean * 0.50))
    elif urgency == "MEDIUM":
        return max(10, int(rul_mean * 0.70))
    else:  # LOW
        return max(20, int(rul_mean * 0.90))


def compute_expected_cost(
    failure_prob: float,
    c_late: float = C_LATE,
    c_early: float = C_EARLY,
) -> float:
    """
    Expected maintenance cost given current failure probability.

    E[Cost] = P_late * C_late + (1 - P_late) * C_early
    """
    return round(failure_prob * c_late + (1.0 - failure_prob) * c_early, 2)


def compute_savings_vs_reactive(
    failure_prob: float,
    c_late: float = C_LATE,
    c_early: float = C_EARLY,
) -> float:
    """
    Estimated savings compared to a purely reactive strategy
    (i.e., always waiting for failure → always paying C_late).
    """
    reactive_cost = c_late
    optimal_cost = compute_expected_cost(failure_prob, c_late, c_early)
    return round(max(reactive_cost - optimal_cost, 0.0), 2)


def build_recommended_action(urgency: str, rul_mean: float, window: int) -> str:
    actions = {
        "CRITICAL": (
            f"⛔ IMMEDIATE INTERVENTION REQUIRED – "
            f"estimated RUL {rul_mean:.0f} cycles. "
            f"Schedule maintenance within {window} cycle(s)."
        ),
        "HIGH": (
            f"🔴 HIGH RISK – schedule maintenance within {window} cycles. "
            f"Estimated RUL {rul_mean:.0f} cycles."
        ),
        "MEDIUM": (
            f"🟡 ELEVATED RISK – plan maintenance within {window} cycles. "
            f"Estimated RUL {rul_mean:.0f} cycles. Monitor closely."
        ),
        "LOW": (
            f"🟢 NOMINAL – next recommended inspection within {window} cycles. "
            f"Estimated RUL {rul_mean:.0f} cycles."
        ),
    }
    return actions.get(urgency, "No recommendation available.")


# ---------------------------------------------------------------------------
# Engine class (stateless processor, no PipelineComponent overhead)
# ---------------------------------------------------------------------------
class RiskAndCostEngine:
    """
    Processes a FAILURE_METRICS payload and returns a complete RISK_DECISION.
    """

    def __init__(
        self,
        results_dir: str = RESULTS_DIR,
        c_late: float = C_LATE,
        c_early: float = C_EARLY,
    ):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.c_late = c_late
        self.c_early = c_early
        self.logger = logging.getLogger(__name__)

    def process(self, payload: dict) -> dict:
        unit_id = payload.get("unit_id")
        rul_mean = float(payload.get("rul_mean", 0.0))
        rul_std = float(payload.get("rul_std", 1.0))
        failure_prob = float(payload.get("failure_prob_at_horizon", 0.0))
        hazard_rate = float(payload.get("hazard_rate", 0.0))
        alert_level = payload.get("alert_level", "NOMINAL")

        risk_score = compute_risk_score(failure_prob, hazard_rate, rul_mean, rul_std)
        urgency = compute_urgency(risk_score)
        window = compute_intervention_window(rul_mean, urgency)
        expected_cost = compute_expected_cost(failure_prob, self.c_late, self.c_early)
        savings = compute_savings_vs_reactive(failure_prob, self.c_late, self.c_early)
        action = build_recommended_action(urgency, rul_mean, window)

        decision = {
            "type": "RISK_DECISION",
            "unit_id": unit_id,
            "timestamp": payload.get("timestamp", time.time()),
            # Input summary
            "rul_mean": round(rul_mean, 3),
            "rul_std": round(rul_std, 3),
            "failure_prob_at_horizon": round(failure_prob, 6),
            "hazard_rate": round(hazard_rate, 6),
            "alert_level": alert_level,
            # Risk outputs
            "risk_score": risk_score,
            "maintenance_urgency": urgency,
            "intervention_window_cycles": window,
            "recommended_action": action,
            # Economic outputs
            "expected_cost_eur": expected_cost,
            "cost_savings_vs_reactive_eur": savings,
            "optimal_threshold": round(self.c_early / (self.c_late + self.c_early), 4),
            "c_late_eur": self.c_late,
            "c_early_eur": self.c_early,
        }

        self.logger.info(
            f"RiskEngine: unit={unit_id}  risk={risk_score:.3f}  "
            f"urgency={urgency}  E[cost]={expected_cost:.0f}€  "
            f"savings={savings:.0f}€"
        )
        if urgency in ("CRITICAL", "HIGH"):
            self.logger.warning(
                f"RiskEngine: ⚠️  {urgency} – unit {unit_id}  "
                f"risk_score={risk_score:.3f}"
            )

        self._persist(decision)
        return decision

    def _persist(self, decision: dict) -> None:
        path = self.results_dir / "risk_decisions.json"
        existing: list = []
        if path.exists():
            try:
                with open(path) as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
            except Exception:
                existing = []
        existing.append(decision)
        existing = existing[-10_000:]
        with open(path, "w") as f:
            json.dump(existing, f, indent=2)

