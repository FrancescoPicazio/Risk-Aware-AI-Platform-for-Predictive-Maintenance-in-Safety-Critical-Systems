from abc import ABC, abstractmethod


class PipelineComponent(ABC):
    """Classe base per tutti i componenti della pipeline"""

    def __init__(self, name: str):
        self.name = name
        self.is_running = False

    @abstractmethod
    def setup(self) -> None:
        """Inizializzazione del componente"""
        pass

    @abstractmethod
    def execute(self) -> None:
        """Esecuzione logica del componente"""
        pass

    @abstractmethod
    def teardown(self) -> None:
        """Cleanup del componente"""
        pass

    def start(self) -> None:
        """Avvia il componente"""
        self.is_running = True
        self.execute()

    def stop(self) -> None:
        """Ferma il componente"""
        self.is_running = False
        self.teardown()
