from src.containers.scheduler import Scheduler
from src.containers.streaming import Streaming
from src.containers.data_ingestion import DataIngestion
from src.containers.training_pipeline import TrainingPipeline
from src.containers.monitoring_and_drift import MonitoringAndDrift


def main():
    """Entry point della pipeline"""
    scheduler = Scheduler()

    # Istanzia i componenti
    streaming = Streaming()
    data_ingestion = DataIngestion()
    training_pipeline = TrainingPipeline()
    monitoring_and_drift = MonitoringAndDrift()

    # Configura e avvia lo scheduler
    scheduler.schedule_pipeline(
        [streaming, data_ingestion, training_pipeline, monitoring_and_drift]
    )

    scheduler.start()


if __name__ == "__main__":
    main()
