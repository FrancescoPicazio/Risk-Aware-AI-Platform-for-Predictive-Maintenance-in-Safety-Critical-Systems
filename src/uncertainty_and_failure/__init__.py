"""
Uncertainty & Failure Modeling Package
========================================
Active components
-----------------
UncertaintyQuantification   – MC Dropout inference + calibration  (subscribe: cmapss/uncertainty)
ProbabilisticFailureModeling – failure probability + survival curves (subscribe: cmapss/uncertainty)

Deprecated
----------
UncertaintyAndFailure – replaced by the two components above; kept as a re-export stub.
"""

__version__ = "0.4.0"

from src.uncertainty_and_failure.uncertainty_quantification import UncertaintyQuantification
from src.uncertainty_and_failure.probabilistic_failure_modeling import ProbabilisticFailureModeling

__all__ = [
    "UncertaintyQuantification",
    "ProbabilisticFailureModeling",
]
