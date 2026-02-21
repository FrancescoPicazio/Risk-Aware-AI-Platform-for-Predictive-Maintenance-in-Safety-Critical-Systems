from src.containers.base import PipelineComponent


class TrainingPipeline(PipelineComponent):
    def __init__(self):
        super().__init__("TrainingPipeline")

    def setup(self) -> None:
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")
