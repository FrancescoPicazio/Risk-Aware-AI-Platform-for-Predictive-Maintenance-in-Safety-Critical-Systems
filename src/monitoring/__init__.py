"""
Monitoring Package
==================
Active component
----------------
MonitoringDriftModule – full KS drift detection, ECE tracking, retraining trigger,
                        FastAPI sub-app on port 8001.
                        Subscribe: cmapss/monitoring, cmapss/scheduler, cmapss/inference

Deprecated
----------
Monitoring – replaced by MonitoringDriftModule; kept as a re-export alias.
"""

__version__ = "0.3.0"

from src.monitoring.monitoring_drift import MonitoringDriftModule
from src.monitoring.monitoring_drift import MonitoringDriftModule as Monitoring  # backwards compat

__all__ = ["MonitoringDriftModule", "Monitoring"]
