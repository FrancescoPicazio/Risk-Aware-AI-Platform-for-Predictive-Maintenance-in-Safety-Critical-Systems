from src.common.components import PipelineComponent

class Scheduler:
    components = []

    def schedule_pipeline(self, components: list[PipelineComponent]) -> None:
        self.components = components
        print("=== Scheduler setup ===")
        for component in self.components:
            component.setup()

    def start(self) -> None:
        print("=== Scheduler started ===")
        for component in self.components:
            component.start()

if __name__ == "__main__":
    import logging
    import time
    import os

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "="*60)
    print("⏱️  [SCHEDULER CONTAINER ONLINE]")
    print("="*60)
    logger.info(f"Training Schedule: {os.getenv('TRAINING_SCHEDULE', '0 2 * * *')}")
    logger.info(f"Monitoring Schedule: {os.getenv('MONITORING_SCHEDULE', '*/15 * * * *')}")
    print("="*60 + "\n")

    scheduler = Scheduler()

    # TODO: Implement actual scheduling logic
    logger.info("Scheduler initialized - awaiting tasks...")

    try:
        while True:
            time.sleep(60)
            logger.info("⏱️  Scheduler heartbeat...")
    except KeyboardInterrupt:
        logger.info("🛑 Scheduler stopped")
