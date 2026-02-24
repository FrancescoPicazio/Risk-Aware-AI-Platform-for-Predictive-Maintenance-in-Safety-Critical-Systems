import logging
import time

from src.common.components import PipelineComponent
from configs import config

class RiskAndCosts(PipelineComponent):
    def __init__(self):
        super().__init__("RiskAndCosts", config.MQTT["TOPICS"]["RISK_AND_COSTS"])

    def setup(self) -> None:
        super().setup()
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "=" * 60)
    print("⚠️  [RISK & COST ENGINE CONTAINER ONLINE]")
    print("=" * 60 + "\n")

    risk = RiskAndCosts()
    risk.setup()

    try:
        while True:
            risk.execute()
            time.sleep(60)
    except KeyboardInterrupt:
        risk.teardown()
        logger.info("Risk Engine stopped")
