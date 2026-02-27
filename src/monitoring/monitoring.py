import logging
import time
import os

from croniter import croniter

from configs import config
from src.common.components import PipelineComponent
from datetime import datetime
from dateutil.tz import UTC

class Monitoring(PipelineComponent):

    def __init__(self):
        super().__init__("Monitoring", [config.MQTT["TOPICS"]["INFERENCE"]])
        now = datetime.now(UTC)

        self._stream_iter = croniter(config.TIMERS["MONITORING_SCHEDULE"], now)
        self._next_stream = self._stream_iter.get_next(datetime)

    def setup(self) -> None:
        super().setup()
        print(f"{self.name}: setup")

    def execute(self) -> None:
        now = datetime.now(UTC)

        print(f"{self.name}: execute")
        if now >= self._next_stream:
            self.logger.info(f"{self.name}: triggering data streaming at {now.isoformat()}")
            self.send_message(config.MQTT["TOPICS"]["SCHEDULER"],{"type": "STREAMING", "timestamp": time.time()})
            self._next_stream = self._stream_iter.get_next(datetime)

    def teardown(self) -> None:
        print(f"{self.name}: teardown")

    def on_message_received(self, payload: dict) -> None:
        print(f"{self.name}: received message - {payload}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "=" * 60)
    print("[MONITORING & DRIFT DETECTION CONTAINER ONLINE]")
    print("=" * 60)
    logger.info(f"MQTT Broker: {os.getenv('MQTT_BROKER', 'mqtt-broker')}")
    logger.info(f"Metrics Topic: {os.getenv('METRICS_TOPIC', 'monitoring/metrics')}")
    print("=" * 60 + "\n")

    monitoring = Monitoring()
    monitoring.setup()


    try:
        while True:
            monitoring.execute()
    except KeyboardInterrupt:
        monitoring.teardown()
        logger.info("Monitoring stopped")
