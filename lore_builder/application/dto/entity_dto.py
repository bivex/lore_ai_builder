from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from ...domain.model.value_objects import EntityType, CanonStatus


@dataclass(frozen=True)
class GenerateEntityCommand:
    name: str
    entity_type: EntityType
    prompt_hint: str
    era: Optional[str] = None
    year: Optional[int] = None
    relations_hint: List[Dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class EntityResponseDTO:
    entity_id: str
    name: str
    entity_type: str
    summary: str
    description: str
    status: str
    facts: List[str]
    relations: List[Dict[str, str]]
    timeline: Optional[str] = None


@dataclass(frozen=True)
class AuditResultDTO:
    entity_name: str
    is_valid: bool
    contradictions: List[str]
    notes: str
