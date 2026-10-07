from typing import List, Callable, Dict, Type
import logging
from ...domain.model.events import DomainEvent
from ...application.ports.outbound.event_publisher_port import EventPublisherPort

logger = logging.getLogger(__name__)


class InMemoryEventPublisherAdapter(EventPublisherPort):
    """In-memory event dispatcher notifying registered handlers of domain events."""

    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[Callable[[DomainEvent], None]]] = {}
        self.published_events: List[DomainEvent] = []

    def subscribe(self, event_type: Type[DomainEvent], handler: Callable[[DomainEvent], None]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        self.published_events.append(event)
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error handling event {type(event).__name__}: {e}")
