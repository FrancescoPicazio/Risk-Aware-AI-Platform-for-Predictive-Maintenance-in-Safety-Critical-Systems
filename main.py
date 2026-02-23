"""
Local Development Entry Point
===============================
NOTE: This file is NOT used by Docker containers.
      Each Docker service starts autonomously.

This file is useful for:
- Local testing without Docker
- Component debugging
- Rapid development

For Docker usage, see: docker/README.md
"""

from src.scheduler.scheduler import Scheduler
from src.streaming.streaming import Streaming
from src.model.training_pipeline import TrainingPipeline
from src.monitoring.monitoring import Monitoring
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """
    Local entry point to orchestrate components without Docker.

    WARNING: In production, use Docker Compose:
        cd docker
        docker-compose up
    """
    print("\n" + "="*70)
    print("🚀 LOCAL DEVELOPMENT MODE - Running without Docker")
    print("="*70)
    print("⚠️  NOTE: For production, use: cd docker && docker-compose up")
    print("="*70 + "\n")

    logger.info("Initializing local scheduler...")
    scheduler = Scheduler()

    # Instantiate base components
    streaming = Streaming()
    training_pipeline = TrainingPipeline()
    monitoring = Monitoring()

    # Configure and start scheduler
    logger.info("Configuring local pipeline...")
    scheduler.schedule_pipeline(
        [streaming, training_pipeline, monitoring]
    )

    logger.info("▶️  Starting local pipeline...")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("\n🛑 Local pipeline interrupted by user")
        print("\n" + "="*70)
        print("To use Docker: cd docker && docker-compose up")
        print("="*70 + "\n")


if __name__ == "__main__":
    main()
