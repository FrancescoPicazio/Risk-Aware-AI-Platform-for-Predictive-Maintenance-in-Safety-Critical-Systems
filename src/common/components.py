import json
import time
from abc import ABC, abstractmethod
import paho.mqtt.client as mqtt
from configs import config
import os
import logging

class PipelineComponent(ABC):
    """Base class for all pipeline components"""

    def __init__(self, name: str, mqtt_topic_subscribe_list: list[str]= None):
        if mqtt_topic_subscribe_list is None:
            mqtt_topic_subscribe_list = []

        self.name = name
        self.is_running = False
        self._mqtt_client = None
        self.mqtt_broker = os.getenv('MQTT_BROKER', config.MQTT['BROKER'])
        self.mqtt_port = int(os.getenv('MQTT_PORT', config.MQTT['PORT']))
        self.mqtt_topic_subscribe_list = os.getenv('INPUT_TOPIC', mqtt_topic_subscribe_list)
        self.max_retries = config.MQTT['MAX_RETRIES']
        self.retry_delay = config.MQTT['RETRY_DELAY']
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def _on_disconnect(self, _client, _userdata, _disconnect_flags, reason_code, _properties):
        self.logger.warning(f"Disconnected from MQTT Broker. Reason code: {reason_code}")


    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties):
        if reason_code == 0:
            self.logger.info(f"Connected to MQTT Broker at {self.mqtt_broker}:{self.mqtt_port}")
        else:
            self.logger.error(f"Failed to connect to MQTT Broker. Reason code: {reason_code}")

    def _subscribe_channels(self):
        for mqtt_topic_subscribe in self.mqtt_topic_subscribe_list:
            if mqtt_topic_subscribe:
                self._mqtt_client.subscribe(mqtt_topic_subscribe, qos=1)
                self.logger.info(f"Subscribed to topic: {mqtt_topic_subscribe}")

    def setup(self) -> None:
        """Initialize the component and MQTT connection"""
        self._mqtt_client = mqtt.Client(
            client_id=self.name,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_disconnect = self._on_disconnect
        self._mqtt_client.on_message = self._on_message

        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"Attempting to connect to MQTT (attempt {attempt}/{self.max_retries})...")
                self._mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
                self._mqtt_client.loop_start()
                time.sleep(2)
                if self._mqtt_client.is_connected():
                    self.logger.info("Successfully connected to MQTT Broker")
                    self._subscribe_channels()
                    break
            except Exception as e:
                self.logger.warning(f"Connection attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    self.logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error("Max retries reached. Giving up.")
                    raise

    def send_message(self, mqtt_topic_publish:str, payload: dict) -> bool:
        """Send a message to the MQTT broker"""
        if mqtt_topic_publish is None:
            self.logger.error(f"{self.name}: Output topic is not defined. Cannot send message.")
            return False

        if self._mqtt_client and self._mqtt_client.is_connected():
            result = self._mqtt_client.publish(
                mqtt_topic_publish,
                json.dumps(payload),
                qos=1
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"{self.name}: Message sent to {mqtt_topic_publish}")
                return True
            else:
                self.logger.error(f"{self.name}: Failed to publish, rc={result.rc}")
                return False
        else:
            self.logger.error(f"{self.name}: Cannot send message, MQTT client is not connected")
            return False

    def _on_message(self, client, userdata, msg):
        """Internal MQTT message handler"""
        try:
            payload = json.loads(msg.payload.decode())
            self.logger.info(f"{self.name}: Received message on {msg.topic}")
            self.on_message_received(payload)
        except json.JSONDecodeError as e:
            self.logger.error(f"{self.name}: Invalid JSON: {e}")
        except Exception as e:
            self.logger.error(f"{self.name}: Error processing message: {e}")

    @abstractmethod
    def on_message_received(self, payload: dict) -> None:
        """Handle incoming MQTT messages - implement in subclass"""
        pass

    @abstractmethod
    def execute(self) -> None:
        """Execute component logic"""
        pass

    @abstractmethod
    def teardown(self) -> None:
        """Cleanup the component"""
        self.logger.info(f"{self.name}: teardown")
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
            self.logger.info("Disconnected from MQTT Broker")

        self.logger.info("Shutting down streaming component")

    def start(self) -> None:
        """Start the component"""
        self.is_running = True
        self.execute()

    def stop(self) -> None:
        """Stop the component"""
        self.is_running = False
        self.teardown()
