"""
[DEPRECATED] Uncertainty & Failure Probability Module
======================================================
This module has been superseded by the three-stage pipeline:

    1. UncertaintyQuantification   (src/uncertainty_and_failure/uncertainty_quantification.py)
       Subscribe: cmapss/uncertainty  →  Publish: cmapss/risk

    2. ProbabilisticFailureModeling (src/uncertainty_and_failure/probabilistic_failure_modeling.py)
       Subscribe: cmapss/uncertainty  →  Publish: cmapss/risk

    3. RiskDecisionEngine           (src/risk_and_cost/risk_decision_engine.py)
       Subscribe: cmapss/risk         →  Publish: cmapss/economic

The fast-path bridge from streaming inference to the risk topic is provided by:

    RiskAndCostComponent            (src/risk_and_cost/risk_and_costs.py)
       Subscribe: cmapss/inference   →  Publish: cmapss/risk

This file is kept for reference only and is NOT used by any Docker container.
"""

# Legacy re-exports for backwards compatibility with any external imports
from src.uncertainty_and_failure.uncertainty_quantification import UncertaintyQuantification  # noqa: F401
from src.uncertainty_and_failure.probabilistic_failure_modeling import (  # noqa: F401
    compute_unit_failure_profile,
    failure_probability,
    survival_probability,
    hazard_rate,
)

__all__ = [
    "UncertaintyQuantification",
    "compute_unit_failure_profile",
    "failure_probability",
    "survival_probability",
    "hazard_rate",
]
