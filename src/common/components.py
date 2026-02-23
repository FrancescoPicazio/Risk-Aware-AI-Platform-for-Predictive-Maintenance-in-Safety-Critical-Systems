from abc import ABC, abstractmethod

class PipelineComponent(ABC):
    """Base class for all pipeline components"""

    def __init__(self, name: str):
        self.name = name
        self.is_running = False

    @abstractmethod
    def setup(self) -> None:
        """Initialize the component"""
        pass

    @abstractmethod
    def execute(self) -> None:
        """Execute component logic"""
        pass

    @abstractmethod
    def teardown(self) -> None:
        """Cleanup the component"""
        pass

    def start(self) -> None:
        """Start the component"""
        self.is_running = True
        self.execute()

    def stop(self) -> None:
        """Stop the component"""
        self.is_running = False
        self.teardown()
