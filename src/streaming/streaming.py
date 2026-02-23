import logging
import time
import os

from configs import config
from src.common.components import PipelineComponent


class Streaming(PipelineComponent):
    def __init__(self, ):
        super().__init__("Streaming")

    def setup(self) -> None:
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "="*60)
    print("🎬 [STREAMING SIMULATOR CONTAINER ONLINE]")
    print("="*60)
    logger.info(f"MQTT Broker: {os.getenv('MQTT_BROKER', 'mqtt-broker')}")
    logger.info(f"MQTT Port: {os.getenv('MQTT_PORT', '1883')}")
    logger.info(f"Output Topic: {os.getenv('OUTPUT_TOPIC', 'raw/sensors')}")
    print("="*60 + "\n")

    streaming = Streaming()
    streaming.setup()

    try:
        while True:
            streaming.execute()
            time.sleep(config.STREAMING_TIME_INTERVAL)
    except KeyboardInterrupt:
        streaming.teardown()
        logger.info("🛑 Streaming Simulator stopped")


