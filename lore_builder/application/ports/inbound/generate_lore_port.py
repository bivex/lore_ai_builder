from abc import ABC, abstractmethod
from ...dto.entity_dto import GenerateEntityCommand, EntityResponseDTO


class GenerateLoreUseCasePort(ABC):
    """Inbound Driving Port for initiating lore generation."""

    @abstractmethod
    def execute(self, cmd: GenerateEntityCommand) -> EntityResponseDTO:
        pass
