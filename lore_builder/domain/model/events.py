from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, kw_only=True)
class EntityDraftCreated(DomainEvent):
    entity_name: str
    entity_type: str
    session_id: str


@dataclass(frozen=True, kw_only=True)
class EntityAuditRequested(DomainEvent):
    entity_name: str
    facts_to_verify: List[str]


@dataclass(frozen=True, kw_only=True)
class EntityAuditPassed(DomainEvent):
    entity_name: str
    auditor_notes: str


@dataclass(frozen=True, kw_only=True)
class EntityAuditRejected(DomainEvent):
    entity_name: str
    contradictions: List[str]


@dataclass(frozen=True, kw_only=True)
class LoreFactCommitted(DomainEvent):
    fact_id: str
    statement: str
    entity_name: str


@dataclass(frozen=True, kw_only=True)
class ResourceAlertTriggered(DomainEvent):
    session_name: str
    alert_message: str
