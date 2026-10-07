from typing import Optional

from ..ports.inbound.audit_lore_port import AuditLoreUseCasePort
from ..ports.outbound.memory_port import MemoryPort
from ..ports.outbound.event_publisher_port import EventPublisherPort
from ..ports.outbound.jev_decision_port import JevDecisionPort
from ..dto.entity_dto import AuditResultDTO
from ...domain.model.aggregate import LoreEntityAggregate
from ...domain.services.consistency_checker import DomainConsistencyPolicy


class AuditEntityUseCase(AuditLoreUseCasePort):
    """Use case that audits a draft entity against L3 World Bible and L1 facts, accelerated by Jev System-1 typed decisions."""

    def __init__(
        self,
        memory_port: MemoryPort,
        event_publisher: EventPublisherPort,
        jev_port: Optional[JevDecisionPort] = None,
    ):
        self.memory = memory_port
        self.publisher = event_publisher
        self.jev = jev_port

    def execute(self, entity: LoreEntityAggregate) -> AuditResultDTO:
        entity.request_audit()
        self.publisher.publish_all(entity.pull_events())

        world_bible = self.memory.get_world_bible()
        canonical_facts = self.memory.search_canonical_facts(
            query=f"{entity.name} {entity.entity_type.value}", limit=10
        )

        contradictions = []

        jev_details = ""
        # 1. Jev System-1 Calibrated Decision Pass (if available)
        if self.jev:
            narrative = f"{entity.summary} {entity.description}"
            jev_report = self.jev.audit_entity_canon(
                world_rules=world_bible.render_prompt_context(),
                entity_name=entity.name,
                entity_narrative=narrative,
                immutable_laws=world_bible.immutable_laws,
            )
            if jev_report.recommended_verdict != "APPROVE":
                contradictions.append(f"[JEV DECISION ENGINE]: {jev_report.explanation}")
            else:
                jev_details = (
                    f" [Jev System-1: risk={jev_report.lore_distortion_risk.score:.2f}, "
                    f"P_comply={jev_report.is_canon_consistent.p_yes:.2f}]"
                )

        # 2. Domain Consistency Policy (Temporal Algebra & Axioms)
        domain_report = DomainConsistencyPolicy.audit_entity(
            entity=entity,
            world_bible=world_bible,
            canonical_facts=canonical_facts,
        )
        contradictions.extend(domain_report.contradictions)

        is_valid = len(contradictions) == 0
        notes = (
            f"Canon consistency check passed{jev_details}"
            if is_valid
            else f"Detected {len(contradictions)} conflict(s)"
        )

        if is_valid:
            entity.mark_canonical(auditor_notes=notes)
        else:
            entity.reject(contradictions=contradictions)

        self.publisher.publish_all(entity.pull_events())

        return AuditResultDTO(
            entity_name=entity.name,
            is_valid=is_valid,
            contradictions=contradictions,
            notes=notes,
        )
