from src.common.components import PipelineComponent


class Monitoring(PipelineComponent):
    def __init__(self):
        super().__init__("Monitoring")

    def setup(self) -> None:
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")


if __name__ == "__main__":
    import logging
    import time
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "=" * 60)
    print("📈 [MONITORING & DRIFT DETECTION CONTAINER ONLINE]")
    print("=" * 60)
    logger.info(f"MQTT Broker: {os.getenv('MQTT_BROKER', 'mqtt-broker')}")
    logger.info(f"Metrics Topic: {os.getenv('METRICS_TOPIC', 'monitoring/metrics')}")
    print("=" * 60 + "\n")

    monitoring = Monitoring()
    monitoring.setup()

    try:
        while True:
            monitoring.execute()
            time.sleep(60)
    except KeyboardInterrupt:
        monitoring.teardown()
        logger.info("🛑 Monitoring stopped")
