from src.common.components import PipelineComponent


class DataIngestion(PipelineComponent):
    def __init__(self):
        super().__init__("DataIngestion")

    def setup(self) -> None:
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")
