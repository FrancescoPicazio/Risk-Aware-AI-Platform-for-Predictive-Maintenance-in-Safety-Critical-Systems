"""
Risk & Cost Assessment – MQTT Container Entry Point
====================================================
Subscribes to:
* ``cmapss/inference``  – type=RUL_PREDICTION  (from TrainingPipeline)

For each incoming RUL prediction it:
1. Computes failure probability + hazard rate from the RUL distribution.
2. Delegates full risk/cost computation to ``RiskAndCostEngine``.
3. Publishes the RISK_DECISION to ``cmapss/risk`` so the downstream
   RiskDecisionEngine, EconomicOptimizationLayer and API can consume it.

Note: this component acts as a fast-path bridge from streaming inference
results to the risk topic, complementing the more detailed UQ pipeline
(UncertaintyQuantification → ProbabilisticFailureModeling → RiskDecisionEngine).
"""

import logging
import math
import time

from configs import config
from src.common.components import PipelineComponent
from src.risk_and_cost.risk_and_cost_engine import RiskAndCostEngine


# ---------------------------------------------------------------------------
# Lightweight failure-probability helpers (no scipy dependency)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erfc."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _quick_failure_metrics(
    rul_mean: float,
    rul_std: float,
    horizon: int = 30,
) -> dict:
    """Derive failure_prob_at_horizon, hazard_rate and alert_level."""
    sigma = max(rul_std, 1e-6)
    z = (horizon - rul_mean) / sigma
    failure_prob = _norm_cdf(z)
    survival = max(1.0 - failure_prob, 1e-9)
    pdf_val = _norm_pdf(z) / sigma
    hazard = pdf_val / survival

    if rul_mean <= 20 or failure_prob >= 0.70:
        alert = "CRITICAL"
    elif rul_mean <= 50 or failure_prob >= 0.30:
        alert = "WARNING"
    else:
        alert = "NOMINAL"

    return {
        "failure_prob_at_horizon": round(failure_prob, 6),
        "hazard_rate": round(hazard, 8),
        "alert_level": alert,
    }


# ---------------------------------------------------------------------------
# PipelineComponent
# ---------------------------------------------------------------------------

class RiskAndCostComponent(PipelineComponent):
    """
    Bridge component: reads RUL_PREDICTION from ``cmapss/inference`` and
    publishes a full RISK_DECISION to ``cmapss/risk``.

    This ensures that streaming inference results immediately reach the
    risk / economic downstream without waiting for the full UQ pipeline.
    """

    def __init__(self):
        super().__init__(
            "RiskAndCost",
            [config.MQTT["TOPICS"]["INFERENCE"]],
        )
        self._engine = RiskAndCostEngine(
            results_dir=config.DATA["RESULTS"],
        )
        self._queue: list = []

    def setup(self) -> None:
        super().setup()
        self.logger.info(
            f"{self.name}: setup complete – "
            f"subscribe=cmapss/inference  publish=cmapss/risk"
        )

    # -----------------------------------------------------------------------
    # MQTT callback
    # -----------------------------------------------------------------------
    def on_message_received(self, payload: dict) -> None:
        if payload.get("type") == "RUL_PREDICTION":
            self._queue.append(payload)

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------
    def execute(self) -> None:
        while self._queue:
            item = self._queue.pop(0)
            try:
                self._process(item)
            except Exception as exc:
                self.logger.error(
                    f"{self.name}: error processing item – {exc}"
                )

    def _process(self, payload: dict) -> None:
        """Enrich a RUL_PREDICTION with risk/cost metrics and publish."""
        rul_mean = float(payload.get("rul_mean", 0.0))
        rul_std = float(payload.get("rul_std", 1.0))

        # Derive failure metrics inline (no extra container dependency)
        fm = _quick_failure_metrics(rul_mean, rul_std)

        enriched = {
            **payload,
            **fm,
        }

        decision = self._engine.process(enriched)

        # Publish to cmapss/risk (consumed by RiskDecisionEngine, API, Monitoring)
        self.send_message(config.MQTT["TOPICS"]["RISK"], decision)

        self.logger.info(
            f"{self.name}: unit={decision.get('unit_id')}  "
            f"risk={decision.get('risk_score', 0.0):.3f}  "
            f"urgency={decision.get('maintenance_urgency')}  "
            f"E[cost]={decision.get('expected_cost_eur', 0.0):.0f}€"
        )

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("\n" + "=" * 60)
    print("⚠️  [RISK & COST ENGINE CONTAINER ONLINE]")
    print("   subscribe: cmapss/inference")
    print("   publish  : cmapss/risk")
    print("=" * 60 + "\n")

    component = RiskAndCostComponent()
    component.setup()

    try:
        while True:
            component.execute()
            time.sleep(0.5)
    except KeyboardInterrupt:
        component.teardown()
        logging.getLogger(__name__).info("🛑 Risk & Cost Engine stopped")
