import logging
import time
import os

from configs import config
from src.common.components import PipelineComponent

class TrainingPipeline(PipelineComponent):
    def __init__(self):
        super().__init__("TrainingPipeline")

    def setup(self) -> None:
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")


if __name__ == "__main__":


    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Container startup banner
    print("\n" + "="*60)
    print("🧠 [TRAINING PIPELINE CONTAINER ONLINE]")
    print("="*60)
    logger.info(f"Model Output Path: {os.getenv('MODEL_OUTPUT_PATH', '/app/data/model_artifacts')}")
    print("="*60 + "\n")

    training = TrainingPipeline()
    training.setup()

    try:
        while True:
            training.execute()
            logger.info("✅ Training completed")
            time.sleep(config.TRAINING_TIME_INTERVAL)
    except KeyboardInterrupt:
        training.teardown()
        logger.info("🛑 Training stopped")


