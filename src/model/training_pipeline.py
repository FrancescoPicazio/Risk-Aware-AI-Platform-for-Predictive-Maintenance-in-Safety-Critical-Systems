import logging
import time
import os

from croniter import croniter

from configs import config
from src.common.components import PipelineComponent
from datetime import datetime
from dateutil.tz import UTC


class TrainingPipeline(PipelineComponent):
    def __init__(self):
        super().__init__("TrainingPipeline", [config.MQTT["TOPICS"]["FEATURE_ENGINEERING"]])
        now = datetime.now(UTC)

        self._stream_iter = croniter(config.TIMERS["TRAINING_SCHEDULE"], now)
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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "="*60)
    print("[TRAINING PIPELINE CONTAINER ONLINE]")
    print("="*60)
    logger.info(f"Model Output Path: {os.getenv('MODEL_OUTPUT_PATH', '/app/data/model_artifacts')}")
    print("="*60 + "\n")

    training = TrainingPipeline()
    training.setup()

    try:
        while True:
            training.execute()
    except KeyboardInterrupt:
        training.teardown()
        logger.info("Training stopped")


