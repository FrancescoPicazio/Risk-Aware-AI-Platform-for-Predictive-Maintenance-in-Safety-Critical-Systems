import logging
import time
import os
import json
import paho.mqtt.client as mqtt

from configs import config
from src.common.components import PipelineComponent


class Streaming(PipelineComponent):
    _experiment_files = []
    _mqtt_client = None

    def __init__(self):
        super().__init__("Streaming")

        # MQTT Configuration
        self.mqtt_broker = os.getenv('MQTT_BROKER', config.MQTT['BROKER'])
        self.mqtt_port = int(os.getenv('MQTT_PORT', config.MQTT['PORT']))
        self.input_topic = os.getenv('INPUT_TOPIC', config.MQTT['INPUT_TOPIC'])

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logging.info(f"Connected to MQTT Broker at {self.mqtt_broker}:{self.mqtt_port}")
        else:
            logging.error(f"Failed to connect to MQTT Broker. Reason code: {reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logging.warning(f"Disconnected from MQTT Broker. Reason code: {reason_code}")

    def verify_single_file(self, file_path):
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Expected file not found: {file_path}")

        if os.path.getsize(file_path) == 0:
            raise ValueError(f"File is empty: {file_path}")

        return True

    def _verify_data_files(self):
        files = os.listdir(config.DATA_PATH)
        if not files:
            raise FileNotFoundError(f"No data files found in {config.DATA_PATH}")

        rul_files = [f for f in files if f.startswith("RUL")]
        test_files = [f for f in files if f.startswith("test")]
        train_files = [f for f in files if f.startswith("train")]

        if len(rul_files) == len(test_files) == len(train_files):
            for f in files:
                self.verify_single_file(os.path.join(config.DATA_PATH, f))
            return True
        else:
            raise ValueError(f"Data files in {config.DATA_PATH} are not properly structured.")

    def setup(self) -> None:
        logging.info(f"{self.name}: setup")
        logging.info(f"Data integrity check of files in {config.DATA_PATH}...")
        self._verify_data_files()

        files = [f for f in os.listdir(config.DATA_PATH) if not f.startswith("RUL")]
        self._experiment_files = [os.path.join(config.DATA_PATH, f) for f in files]

        # Setup MQTT connection con retry
        self._mqtt_client = mqtt.Client(
            client_id="streaming_simulator",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_disconnect = self._on_disconnect

        # Retry logic per connessione MQTT
        max_retries = 10
        retry_delay = 5  # secondi

        for attempt in range(1, max_retries + 1):
            try:
                logging.info(f"Attempting to connect to MQTT (attempt {attempt}/{max_retries})...")
                self._mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
                self._mqtt_client.loop_start()
                time.sleep(2)  # Aspetta conferma connessione
                if self._mqtt_client.is_connected():
                    logging.info("Successfully connected to MQTT Broker")
                else:
                    logging.info("MQTT client is not connected after connection attempt.")

            except Exception as e:
                logging.warning(f"Connection attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error("Max retries reached. Giving up.")
                    raise

    def execute(self) -> None:
        logging.info(f"{self.name}: execute")
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

                    # Publish to MQTT
                    result = self._mqtt_client.publish(
                        self.input_topic,
                        json.dumps(payload),
                        qos=1
                    )

                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        if idx % 100 == 0:  # Log every 100 records
                            logging.info(f"Published record #{idx} to {self.input_topic}")
                    else:
                        logging.error(f"Failed to publish record #{idx}")

                    time.sleep(config.STREAMING_TIME_INTERVAL)

    def teardown(self) -> None:
        logging.info(f"{self.name}: teardown")
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
            logging.info("🔌 Disconnected from MQTT Broker")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    logging.info("\n" + "=" * 60)
    logging.info("[STREAMING SIMULATOR CONTAINER ONLINE]")

    streaming = Streaming()
    streaming.setup()

    try:
        streaming.execute()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    finally:
        streaming.teardown()
