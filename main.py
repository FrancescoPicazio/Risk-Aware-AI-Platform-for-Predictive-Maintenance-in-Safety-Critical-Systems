from src.scheduler.scheduler import Scheduler
from src.streaming.streaming import Streaming
from src.model.training_pipeline import TrainingPipeline
from src.monitoring.monitoring_and_drift import MonitoringAndDrift
import configs.config

def main():
    """Entry point della pipeline"""
    scheduler = Scheduler()

    # Istanzia i componenti
    streaming = Streaming(configs.STREAMING_TIME_INTERVAL)
    training_pipeline = TrainingPipeline(configs.TRAINING_TIME_INTERVAL)
    monitoring_and_drift = MonitoringAndDrift(configs.MONITORING_TIME_INTERVAL)

    # Configura e avvia lo scheduler
    scheduler.schedule_pipeline(
        [streaming, training_pipeline, monitoring_and_drift]
    )

    scheduler.start()


if __name__ == "__main__":
    main()
