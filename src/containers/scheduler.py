from src.containers.base import PipelineComponent

class Scheduler:
    components = []

    def schedule_pipeline(self, components: list[PipelineComponent]) -> None:
        self.components = components
        print("=== Scheduler setup ===")
        for component in self.components:
            component.setup()

    def start(self) -> None:
        print("=== Scheduler avviato ===")
        for component in self.components:
            component.start()