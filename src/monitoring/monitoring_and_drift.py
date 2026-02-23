from src.common.components import PipelineComponent


class MonitoringAndDrift(PipelineComponent):
    def __init__(self):
        super().__init__("MonitoringAndDrift")

    def setup(self) -> None:
        print(f"{self.name}: setup")

    def execute(self) -> None:
        print(f"{self.name}: execute")

    def teardown(self) -> None:
        print(f"{self.name}: teardown")
