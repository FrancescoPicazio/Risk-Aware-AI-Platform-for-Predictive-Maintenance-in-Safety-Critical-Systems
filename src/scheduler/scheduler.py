import time
from datetime import datetime

from croniter import croniter
from dateutil.tz import UTC

from configs import config
from src.common.components import PipelineComponent

class Scheduler(PipelineComponent):

    def __init__(self):
        self.name = "Scheduler"
        super().__init__("Scheduler")

        now = datetime.now(UTC)
        self._stream_iter = croniter(config.TIMERS["STREAMING_REPEAT_PAUSE"], now)
        self._training_iter = croniter(config.TIMERS["TRAINING_SCHEDULE"], now)
        self._monitoring_iter = croniter(config.TIMERS["MONITORING_SCHEDULE"], now)

        self._next_stream = self._stream_iter.get_next(datetime)
        self._next_training = self._training_iter.get_next(datetime)
        self._next_monitoring = self._monitoring_iter.get_next(datetime)



    def setup(self):
        super().setup()

    def start(self) -> None:
        print("=== Scheduler started ===")

    def on_message_received(self, payload: dict) -> None:
        print(f"{self.name}: message received - {payload}")

    def execute(self) -> None:
        now = datetime.now(UTC)

        if now >= self._next_stream:
            self.logger.info(f"{self.name}: triggering data streaming at {now.isoformat()}")
            self.send_message(config.MQTT["TOPICS"]["SCHEDULER"],{"type": "STREAMING", "timestamp": time.time()})
            self._next_stream = self._stream_iter.get_next(datetime)

        if now >= self._next_training:
            self.logger.info(f"{self.name}: triggering model training at {now.isoformat()}")
            self.send_message(config.MQTT["TOPICS"]["SCHEDULER"],{"type": "TRAINING", "timestamp": time.time()})
            self._next_training = self._training_iter.get_next(datetime)

        if now >= self._next_monitoring:
            self.logger.info(f"{self.name}: triggering monitoring at {now.isoformat()}")
            self.send_message(config.MQTT["TOPICS"]["SCHEDULER"],{"type": "MONITORING", "timestamp": time.time()})
            self._next_monitoring = self._monitoring_iter.get_next(datetime)

        time.sleep(config.TIMERS["STREAMING"])

    def teardown(self) -> None:
        super().teardown()
        print(f"{self.name}: teardown")

if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.setup()

    try:
        while True:
            scheduler.execute()
    except KeyboardInterrupt:
        pass

    scheduler.teardown()
