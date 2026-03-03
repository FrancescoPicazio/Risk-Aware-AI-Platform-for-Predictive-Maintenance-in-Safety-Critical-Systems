"""
Local Development Entry Point
===============================
NOTE: This file is NOT used by Docker containers.
      Each Docker service starts autonomously.

This file is useful for:
- Local testing without Docker
- Component debugging
- Rapid development

For Docker usage, see: docker/docker-compose.yml

Pipeline flow
-------------
Scheduler ──MQTT──► Streaming ──MQTT──► DataIngestion ──MQTT──► FeatureEngineering
                                                                       │
                                                           MQTT (FEATURES_READY)
                                                                       ▼
Scheduler ──MQTT──► TrainingPipeline ◄──────────────────────────────────
                                   │
                              MQTT (RUL_PREDICTION / TRAINING_COMPLETE)
                                   ▼
Scheduler ──MQTT──► Monitoring ◄─────────────────────────────────────
"""

import threading
import time

from src.scheduler.scheduler import Scheduler
from src.streaming.streaming import Streaming
from src.data_ingestion.data_ingestion import DataIngestion
from src.feature_engineering.feature_engineering import FeatureEngineering
from src.model.training_pipeline import TrainingPipeline
from src.monitoring.monitoring import Monitoring
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _run_loop(component, sleep: float = 0.05):
    """Run a component's execute() method in a tight loop on a daemon thread."""
    while True:
        try:
            component.execute()
        except Exception as e:
            logger.error(f"{component.name}: unhandled error in execute() – {e}")
        time.sleep(sleep)


def main():
    logger.info("Initialising local pipeline …")

    # Instantiate all components
    scheduler = Scheduler()
    streaming = Streaming()
    ingestion = DataIngestion()
    feature_eng = FeatureEngineering()
    training = TrainingPipeline()
    monitoring = Monitoring()

    # Setup (connects to MQTT and subscribes)
    for component in [scheduler, streaming, ingestion, feature_eng, training, monitoring]:
        component.setup()

    logger.info("All components connected to MQTT. Starting execution loops …")
    print("\n" + "=" * 70)
    print("🚀 Risk-Aware Predictive Maintenance Platform – LOCAL MODE")
    print("   Press Ctrl+C to stop")
    print("=" * 70 + "\n")

    # Run all components concurrently on daemon threads
    threads = [
        threading.Thread(target=_run_loop, args=(scheduler, 1.0),      daemon=True, name="scheduler"),
        threading.Thread(target=_run_loop, args=(streaming, 0.0),       daemon=True, name="streaming"),
        threading.Thread(target=_run_loop, args=(ingestion, 0.05),      daemon=True, name="ingestion"),
        threading.Thread(target=_run_loop, args=(feature_eng, 0.05),    daemon=True, name="feature_eng"),
        threading.Thread(target=_run_loop, args=(training, 0.1),        daemon=True, name="training"),
        threading.Thread(target=_run_loop, args=(monitoring, 1.0),      daemon=True, name="monitoring"),
    ]

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("\nLocal pipeline interrupted by user")
        print("\n" + "=" * 70)
        print("Shutting down … (for Docker: cd docker && docker-compose up)")
        print("=" * 70 + "\n")
        for component in [scheduler, streaming, ingestion, feature_eng, training, monitoring]:
            try:
                component.teardown()
            except Exception:
                pass


if __name__ == "__main__":
    main()
