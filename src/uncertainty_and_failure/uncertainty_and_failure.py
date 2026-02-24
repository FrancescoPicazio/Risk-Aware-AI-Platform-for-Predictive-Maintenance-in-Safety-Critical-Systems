from src.common.components import PipelineComponent
from configs import config

class UncertaintyAndFailure(PipelineComponent):
    def __init__(self):
        super().__init__("UncertaintyAndFailure", config.MQTT["TOPICS"]["UNCERTAINTY_AND_FAILURE"])

    def setup(self) -> None:
        super().setup()
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
    print("📊 [UNCERTAINTY & FAILURE CONTAINER ONLINE]")
    print("=" * 60)
    logger.info(f"MQTT Broker: {os.getenv('MQTT_BROKER', 'mqtt-broker')}")
    logger.info(f"Input Topic: {os.getenv('INPUT_TOPIC', 'predictions/rul')}")
    logger.info(f"Output Topic: {os.getenv('OUTPUT_TOPIC', 'predictions/uncertainty')}")
    logger.info(f"Model Path: {os.getenv('MODEL_PATH', '/app/data/model_artifacts')}")
    print("=" * 60 + "\n")

    uq = UncertaintyAndFailure()
    uq.setup()

    try:
        while True:
            uq.execute()
            time.sleep(60)
    except KeyboardInterrupt:
        uq.teardown()
        logger.info("🛑 Uncertainty service stopped")
