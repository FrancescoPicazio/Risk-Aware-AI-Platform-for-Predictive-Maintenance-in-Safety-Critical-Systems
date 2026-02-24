import logging
import time
import os

from configs import config
from src.common.components import PipelineComponent


def verify_single_file(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Expected file not found: {file_path}")

    if os.path.getsize(file_path) == 0:
        raise ValueError(f"File is empty: {file_path}")

    return True

def _verify_data_files():
    data_dir = config.DATA["RAW"]
    files = os.listdir(data_dir)
    if not files:
        raise FileNotFoundError(f"No data files found in {data_dir}")

    rul_files = [f for f in files if f.startswith("RUL")]
    test_files = [f for f in files if f.startswith("test")]
    train_files = [f for f in files if f.startswith("train")]

    if len(rul_files) == len(test_files) == len(train_files):
        for f in files:
            verify_single_file(os.path.join(data_dir, f))
        return True
    else:
        raise ValueError(f"Data files in {data_dir} are not properly structured.")



class Streaming(PipelineComponent):
    _experiment_files = []
    enabled = False
    is_streaming = False

    def __init__(self):
        super().__init__("Streaming", [config.MQTT["TOPICS"]["SCHEDULER"]])

    def setup(self) -> None:
        super().setup()
        data_dir = config.DATA["RAW"]
        logging.info(f"Data integrity check of files in {data_dir}...")
        _verify_data_files()

        files = [f for f in os.listdir(data_dir) if not f.startswith("RUL")]
        self._experiment_files = [os.path.join(data_dir, f) for f in files]
        logging.info(f"{self.name}: setup completed")


    def execute(self) -> None:
        logging.info(f"{self.name}: execute")
        logging.info("Waiting from scheduler to trigger data streaming...")
        self.is_streaming = True
        try:
            for experiment_file in self._experiment_files:
                logging.info(f"Streaming data from: {experiment_file}")
                with open(experiment_file, 'r') as f:
                    for idx, line in enumerate(f, 1):
                        # Parse line (CMAPSS format)
                        values = line.strip().split()
                        # Create JSON payload
                        payload = {
                            "unit_id": int(values[0]),
                            "cycle": int(values[1]),
                            "operational_settings": [float(values[2]), float(values[3]), float(values[4])],
                            "sensor_measurements": [float(v) for v in values[5:]],
                            "timestamp": time.time(),
                            "source_file": os.path.basename(experiment_file)
                        }
                        is_message_sent = self.send_message(config.MQTT["TOPICS"]["DATA_INGESTION"],payload)
                        if idx % 100 == 0 and is_message_sent:
                            logging.info(f"Streamed {idx} lines from {experiment_file}")
                        elif not is_message_sent:
                            logging.error(f"Failed to publish record #{idx}")
                        time.sleep(config.TIMERS["STREAMING"]) # Simulate real-time streaming
        except Exception as e:
            logging.error(f"Error during streaming: {e}")

        self.is_streaming = False

    def on_message_received(self, payload: dict) -> None:
        print(f"{self.name}: message received - {payload}")
        if not self.is_streaming:
            self.enabled = payload["type"] == "STREAMING"
        else:
            logging.warning(f"{self.name}: Received new streaming trigger while already streaming. Ignoring new trigger until current streaming is complete.")

    def teardown(self) -> None:
        super().teardown()


if __name__ == "__main__":
    streaming = Streaming()
    streaming.setup()

    try:
        while True:
            if streaming.enabled:
                streaming.enabled = False
                streaming.execute()

    except KeyboardInterrupt:
        pass
    streaming.teardown()
