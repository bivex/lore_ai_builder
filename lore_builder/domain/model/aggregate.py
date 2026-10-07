from dataclasses import dataclass, field
from typing import List, Optional
import uuid

from .value_objects import EntityType, CanonStatus, EntityRelation, TimelinePoint, RelationType
from .entity import LoreFact
from .events import (
    DomainEvent,
    EntityDraftCreated,
    EntityAuditRequested,
    EntityAuditPassed,
    EntityAuditRejected,
    LoreFactCommitted,
)
from ..exceptions import InvalidEntityStateError


@dataclass
class WorldBibleAggregate:
    """Aggregate Root for L3 Core — Immutable world rules, axioms, and cosmology."""
    world_id: str
    name: str
    cosmology: str
    immutable_laws: List[str] = field(default_factory=list)
    tone: str = "mythic_fantasy"

    def render_prompt_context(self) -> str:
        laws_formatted = "\n".join(f"  - {law}" for law in self.immutable_laws)
        return (
            f"=== WORLD CANON: {self.name} ===\n"
            f"TONE: {self.tone}\n"
            f"COSMOLOGY: {self.cosmology}\n"
            f"IMMUTABLE LAWS:\n{laws_formatted}\n"
            f"================================="
        )


@dataclass
class LoreEntityAggregate:
    """Aggregate Root for any lore entity (Character, Faction, Location, Artifact)."""
    entity_id: str
    name: str
    entity_type: EntityType
    summary: str
    description: str
    timeline_point: Optional[TimelinePoint] = None
    relations: List[EntityRelation] = field(default_factory=list)
    facts: List[LoreFact] = field(default_factory=list)
    status: CanonStatus = CanonStatus.DRAFT
    _events: List[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create_draft(
        cls,
        name: str,
        entity_type: EntityType,
        summary: str,
        description: str,
        timeline_point: Optional[TimelinePoint] = None,
        session_id: str = "",
    ) -> "LoreEntityAggregate":
        entity = cls(
            entity_id=str(uuid.uuid4())[:8],
            name=name,
            entity_type=entity_type,
            summary=summary,
            description=description,
            timeline_point=timeline_point,
            status=CanonStatus.DRAFT,
        )
        entity._record_event(
            EntityDraftCreated(entity_name=name, entity_type=entity_type.value, session_id=session_id)
        )
        return entity

    def request_audit(self) -> None:
        if self.status != CanonStatus.DRAFT:
            raise InvalidEntityStateError(
                f"Cannot request audit for entity '{self.name}' in status '{self.status}'"
            )
        self.status = CanonStatus.AUDITING
        fact_statements = [f.statement for f in self.facts] or [self.summary]
        self._record_event(
            EntityAuditRequested(entity_name=self.name, facts_to_verify=fact_statements)
        )

    def mark_canonical(self, auditor_notes: str = "Verified consistent") -> None:
        if self.status != CanonStatus.AUDITING:
            raise InvalidEntityStateError(
                f"Entity '{self.name}' must be in AUDITING status to become canonical, currently '{self.status}'"
            )
        self.status = CanonStatus.CANONICAL
        self._record_event(EntityAuditPassed(entity_name=self.name, auditor_notes=auditor_notes))

    def reject(self, contradictions: List[str]) -> None:
        self.status = CanonStatus.REJECTED
        self._record_event(EntityAuditRejected(entity_name=self.name, contradictions=contradictions))

    def add_relation(self, target_name: str, relation_type: RelationType, context: Optional[str] = None) -> None:
        self.relations.append(
            EntityRelation(target_entity_name=target_name, relation_type=relation_type, context=context)
        )

    def add_fact(self, statement: str, tags: Optional[List[str]] = None) -> LoreFact:
        fact = LoreFact(
            fact_id=f"f_{str(uuid.uuid4())[:8]}",
            entity_name=self.name,
            statement=statement,
            tags=tags or [self.entity_type.value],
        )
        self.facts.append(fact)
        self._record_event(
            LoreFactCommitted(fact_id=fact.fact_id, statement=statement, entity_name=self.name)
        )
        return fact

    def pull_events(self) -> List[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def _record_event(self, event: DomainEvent) -> None:
        self._events.append(event)
