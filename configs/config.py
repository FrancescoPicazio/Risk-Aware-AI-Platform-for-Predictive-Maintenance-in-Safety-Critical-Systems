DATA = {
    "RAW": "data/raw",
    "PROCESSED": "data/processed",
    "MODEL_ARTIFACTS": "data/model_artifacts",
    "METRICS": "data/metrics",
    "RESULTS": "data/results",
    "METRICS_AND_RESULTS": "data/metrics_and_results"
}

TIMERS = {
    "STREAMING": 0.1, #s
    "STREAMING_REPEAT_PAUSE": '*/1 * * * *', # Every 1 minute
    "TRAINING_SCHEDULE": '0 2 * * *', # At 2:00 AM every day
    "MONITORING_SCHEDULE": '*/15 * * * *', # Every 15 minutes
    "RECAP_SCHEDULE": '0 8 * * *' # At 8:00 AM every day
}


MQTT = {
    "BROKER": "risk-aware-mqtt",
    "PORT": 1883,
    "TOPICS": {
        "SCHEDULER": "cmapss/scheduler",
        "STREAMING": "cmapss/streaming",
        "DATA_INGESTION": "cmapss/data_ingestion",
        "FEATURE_ENGINEERING": "cmapss/feature_engineering",
        "TRAINING": "cmapss/training",
        "UNCERTAINTY_AND_FAILURE": "cmapss/uncertainty_failure",
        "UNCERTAINTY": "cmapss/uncertainty",
        "RISK": "cmapss/risk",
        "RISK_AND_COST": "cmapss/risk_cost",
        "ECONOMIC": "cmapss/economic",
        "INFERENCE": "cmapss/inference",
        "MONITORING": "cmapss/monitoring"
    },
    "MAX_RETRIES": 10,
    "RETRY_DELAY": 5 # seconds
}