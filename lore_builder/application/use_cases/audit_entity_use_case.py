from ..ports.inbound.audit_lore_port import AuditLoreUseCasePort
from ..ports.outbound.memory_port import MemoryPort
from ..ports.outbound.event_publisher_port import EventPublisherPort
from ..dto.entity_dto import AuditResultDTO
from ...domain.model.aggregate import LoreEntityAggregate
from ...domain.services.consistency_checker import DomainConsistencyPolicy


class AuditEntityUseCase(AuditLoreUseCasePort):
    """Use case that audits a draft entity against L3 World Bible and L1 facts."""

    def __init__(self, memory_port: MemoryPort, event_publisher: EventPublisherPort):
        self.memory = memory_port
        self.publisher = event_publisher

    def execute(self, entity: LoreEntityAggregate) -> AuditResultDTO:
        entity.request_audit()
        self.publisher.publish_all(entity.pull_events())

        world_bible = self.memory.get_world_bible()
        canonical_facts = self.memory.search_canonical_facts(
            query=f"{entity.name} {entity.entity_type.value}", limit=10
        )

        report = DomainConsistencyPolicy.audit_entity(
            entity=entity,
            world_bible=world_bible,
            canonical_facts=canonical_facts,
        )

        if report.is_valid:
            entity.mark_canonical(auditor_notes=report.notes)
        else:
            entity.reject(contradictions=report.contradictions)

        self.publisher.publish_all(entity.pull_events())

        return AuditResultDTO(
            entity_name=entity.name,
            is_valid=report.is_valid,
            contradictions=report.contradictions,
            notes=report.notes,
        )
