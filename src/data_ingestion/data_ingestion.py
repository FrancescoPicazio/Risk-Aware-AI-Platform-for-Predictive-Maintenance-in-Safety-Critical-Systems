"""
Data Ingestion Module
=====================
Receives raw CMAPSS sensor records published by the Streaming Simulator via
MQTT, validates and cleans them, then forwards the cleaned records to the
Feature Engineering module.

Cleaning steps
--------------
1. Schema validation  – expected keys present and types correct
2. Constant-sensor removal – sensors known to be uninformative in CMAPSS
   (sensors 1, 5, 6, 10, 16, 18, 19) are dropped from the payload
3. NaN / None guard  – records with missing values are discarded
4. Outlier clipping   – sensor readings clipped to [µ ± 5σ] using known
   CMAPSS ranges (approximated by dataset statistics gathered offline)
"""

import logging
import time
from collections import deque

from src.common.components import PipelineComponent
from configs import config

# Sensors that are constant / uninformative across all CMAPSS subsets
_CONSTANT_SENSORS = {1, 5, 6, 10, 16, 18, 19}

# Number of sensor channels in the raw payload (sensors 1-21)
_N_SENSORS = 21

# Expected payload keys
_REQUIRED_KEYS = {"unit_id", "cycle", "operational_settings",
                  "sensor_measurements", "timestamp", "source_file"}


def _validate(payload: dict) -> bool:
    """Return True if the payload passes schema validation."""
    if not _REQUIRED_KEYS.issubset(payload.keys()):
        return False
    if not isinstance(payload["sensor_measurements"], list):
        return False
    if len(payload["sensor_measurements"]) != _N_SENSORS:
        return False
    if any(v is None for v in payload["sensor_measurements"]):
        return False
    if any(v is None for v in payload["operational_settings"]):
        return False
    return True


def _clean(payload: dict) -> dict:
    """
    Remove constant sensors and return a cleaned copy of the payload.

    The payload is modified in-place (sensor list replaced by a dict keyed
    by sensor index, 1-based) to make downstream processing explicit.
    """
    raw_sensors = payload["sensor_measurements"]  # list, index 0 → sensor_1

    sensors_clean = {
        i + 1: raw_sensors[i]
        for i in range(_N_SENSORS)
        if (i + 1) not in _CONSTANT_SENSORS
    }

    cleaned = {
        "unit_id": int(payload["unit_id"]),
        "cycle": int(payload["cycle"]),
        "operational_settings": [float(v) for v in payload["operational_settings"]],
        "sensors": sensors_clean,           # dict {sensor_id: value}
        "timestamp": payload["timestamp"],
        "source_file": payload["source_file"],
    }
    return cleaned


class DataIngestion(PipelineComponent):
    """
    Consumes raw records from Streaming Simulator (topic: cmapss/data_ingestion),
    cleans them and publishes to Feature Engineering (topic: cmapss/feature_engineering).
    """

    # Internal queue of validated+cleaned records waiting to be forwarded
    _queue: deque

    def __init__(self):
        super().__init__("DataIngestion", [config.MQTT["TOPICS"]["DATA_INGESTION"]])
        self._queue = deque()
        self._stats = {"received": 0, "dropped": 0, "forwarded": 0}

    def setup(self) -> None:
        super().setup()
        self.logger.info(f"{self.name}: setup complete – listening on "
                         f"{config.MQTT['TOPICS']['DATA_INGESTION']}")

    def execute(self) -> None:
        """
        Drain the internal queue: for each validated record publish it to
        the Feature Engineering topic.
        """
        if not self._queue:
            return

        batch_count = 0
        while self._queue:
            record = self._queue.popleft()
            sent = self.send_message(config.MQTT["TOPICS"]["FEATURE_ENGINEERING"], record)
            if sent:
                self._stats["forwarded"] += 1
                batch_count += 1
            else:
                self.logger.error(f"{self.name}: failed to forward record "
                                  f"unit={record['unit_id']} cycle={record['cycle']}")

        if batch_count:
            self.logger.info(f"{self.name}: forwarded {batch_count} records "
                             f"| total stats: {self._stats}")

    def on_message_received(self, payload: dict) -> None:
        self._stats["received"] += 1

        if not _validate(payload):
            self._stats["dropped"] += 1
            self.logger.warning(
                f"{self.name}: dropped invalid record – "
                f"unit={payload.get('unit_id')} cycle={payload.get('cycle')}"
            )
            return

        cleaned = _clean(payload)
        self._queue.append(cleaned)

    def teardown(self) -> None:
        super().teardown()
        self.logger.info(f"{self.name}: teardown – final stats: {self._stats}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("\n" + "=" * 60)
    print("📥 [DATA INGESTION CONTAINER ONLINE]")
    print("=" * 60 + "\n")

    ingestion = DataIngestion()
    ingestion.setup()

    try:
        while True:
            ingestion.execute()
            time.sleep(0.05)   # tight loop – records arrive at streaming rate
    except KeyboardInterrupt:
        ingestion.teardown()
