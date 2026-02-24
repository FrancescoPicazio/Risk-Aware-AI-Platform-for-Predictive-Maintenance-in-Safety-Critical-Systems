import time

from src.common.components import PipelineComponent

from configs import config


class DataIngestion(PipelineComponent):
    _payload = None

    def __init__(self):
        super().__init__("DataIngestion", [config.MQTT["TOPICS"]["SCHEDULER"]])

    def setup(self) -> None:
        super().setup()
        print(f"{self.name}: setup")

    def execute(self) -> None:
        if not self._payload:
            return

        print(f"{self.name}: processing payload - {self._payload}")
        payload = self._payload.copy()
        self._payload = None
        print(f"{self.name}: execute payload - {payload}")
        self.send_message(config.MQTT["TOPICS"]["FEATURE_ENGINEERING"], payload)

    def on_message_received(self, payload: dict) -> None:
        print(f"{self.name}: message received - {payload}")
        self._payload = payload

    def teardown(self) -> None:
        print(f"{self.name}: teardown")


if __name__ == "__main__":
    ingestion = DataIngestion()
    ingestion.setup()

    try:
        while True:
            ingestion.execute()
    except KeyboardInterrupt:
        ingestion.teardown()

