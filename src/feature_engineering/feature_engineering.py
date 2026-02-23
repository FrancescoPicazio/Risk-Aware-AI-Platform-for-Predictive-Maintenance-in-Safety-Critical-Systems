from src.common.components import PipelineComponent


class FeatureEngineering(PipelineComponent):
    def __init__(self):
        super().__init__("FeatureEngineering")

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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "="*60)
    print("⚙️ [FEATURE ENGINEERING CONTAINER ONLINE]")
    print("="*60)
    logger.info(f"MQTT Broker: {os.getenv('MQTT_BROKER', 'mqtt-broker')}")
    logger.info(f"Input Topic: {os.getenv('INPUT_TOPIC', 'validated/data')}")
    logger.info(f"Output Topic: {os.getenv('OUTPUT_TOPIC', 'processed/features')}")
    print("="*60 + "\n")

    fe = FeatureEngineering()
    fe.setup()

    try:
        while True:
            fe.execute()
            time.sleep(60)
    except KeyboardInterrupt:
        fe.teardown()
        logger.info("🛑 Feature Engineering stopped")


