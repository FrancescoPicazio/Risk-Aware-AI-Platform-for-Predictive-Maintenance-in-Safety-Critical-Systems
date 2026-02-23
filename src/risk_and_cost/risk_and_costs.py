from src.common.components import PipelineComponent


class RiskAndCosts(PipelineComponent):
    def __init__(self):
        super().__init__("RiskAndCosts")

    def setup(self) -> None:
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")


if __name__ == "__main__":
    import logging
    import time
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "=" * 60)
    print("⚠️  [RISK & COST ENGINE CONTAINER ONLINE]")
    print("=" * 60)
    logger.info(f"MQTT Broker: {os.getenv('MQTT_BROKER', 'mqtt-broker')}")
    logger.info(f"Input Topic: {os.getenv('INPUT_TOPIC', 'predictions/uncertainty')}")
    logger.info(f"Output Topic: {os.getenv('OUTPUT_TOPIC', 'decisions/risk')}")
    print("=" * 60 + "\n")

    risk = RiskAndCosts()
    risk.setup()

    try:
        while True:
            risk.execute()
            time.sleep(60)
    except KeyboardInterrupt:
        risk.teardown()
        logger.info("🛑 Risk Engine stopped")
