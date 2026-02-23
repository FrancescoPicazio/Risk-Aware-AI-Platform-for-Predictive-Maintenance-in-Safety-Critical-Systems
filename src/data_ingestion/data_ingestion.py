from src.common.components import PipelineComponent


class DataIngestion(PipelineComponent):
    def __init__(self):
        super().__init__("DataIngestion")

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
    print("📥 [DATA INGESTION CONTAINER ONLINE]")
    print("="*60)
    logger.info(f"MQTT Broker: {os.getenv('MQTT_BROKER', 'mqtt-broker')}")
    logger.info(f"Input Topic: {os.getenv('INPUT_TOPIC', 'raw/sensors')}")
    logger.info(f"Output Topic: {os.getenv('OUTPUT_TOPIC', 'validated/data')}")
    print("="*60 + "\n")

    ingestion = DataIngestion()
    ingestion.setup()

    try:
        while True:
            ingestion.execute()
            time.sleep(60)
    except KeyboardInterrupt:
        ingestion.teardown()
        logger.info("🛑 Data Ingestion stopped")

