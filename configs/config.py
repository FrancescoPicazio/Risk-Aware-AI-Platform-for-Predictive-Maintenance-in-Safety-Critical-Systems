STREAMING_TIME_INTERVAL = 0.1 #s
TRAINING_TIME_INTERVAL = 86400 #s - 24 hours
MONITORING_TIME_INTERVAL = 86400 #s - 24 hours

DATA_PATH = "data/raw"

MQTT = {
    "BROKER": "localhost",
    "PORT": 1883,
    "INPUT_TOPIC": "raw/sensors",
    "OUTPUT_TOPIC": "validated/data",
    "METRICS_TOPIC": "monitoring/metrics"
}