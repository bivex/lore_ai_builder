from abc import ABC, abstractmethod
from ...dto.entity_dto import AuditResultDTO
from ....domain.model.aggregate import LoreEntityAggregate


class AuditLoreUseCasePort(ABC):
    """Inbound Driving Port for auditing a lore entity against canon."""

    @abstractmethod
    def execute(self, entity: LoreEntityAggregate) -> AuditResultDTO:
        pass
