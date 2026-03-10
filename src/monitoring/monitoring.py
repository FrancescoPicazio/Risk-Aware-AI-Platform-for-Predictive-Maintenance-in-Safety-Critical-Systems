"""
[DEPRECATED] Monitoring Module – basic z-score drift detection
==============================================================
This module has been superseded by the full-featured:

    MonitoringDriftModule  (src/monitoring/monitoring_drift.py)

which implements:
    - KS test data drift detection (scipy)
    - Rolling RMSE + NASA score performance drift
    - ECE calibration drift tracking
    - Retraining trigger on cmapss/training
    - Model registry (data/model_artifacts/model_registry.json)
    - FastAPI sub-app on port 8001 (/drift, /model-versions, /drift/history)

The Docker container (Dockerfile.monitoring) runs monitoring_drift.py.
This file is kept for reference only.
"""

# Re-export the new module for any external imports
from src.monitoring.monitoring_drift import MonitoringDriftModule as Monitoring  # noqa: F401

__all__ = ["Monitoring"]
