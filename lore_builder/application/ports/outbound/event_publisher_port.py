from abc import ABC, abstractmethod
from typing import List
from ....domain.model.events import DomainEvent


class EventPublisherPort(ABC):
    """Outbound SPI port for dispatching domain events to subscribers."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        pass

    def publish_all(self, events: List[DomainEvent]) -> None:
        for ev in events:
            self.publish(ev)
