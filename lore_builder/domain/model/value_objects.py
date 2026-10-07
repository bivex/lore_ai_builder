from enum import Enum
from dataclasses import dataclass
from typing import Optional


class EntityType(str, Enum):
    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    ARTIFACT = "artifact"
    HISTORICAL_EVENT = "historical_event"
    ERA = "era"
    MAGIC_SYSTEM = "magic_system"


class CanonStatus(str, Enum):
    DRAFT = "draft"
    AUDITING = "auditing"
    CANONICAL = "canonical"
    REJECTED = "rejected"


class RelationType(str, Enum):
    MEMBER_OF = "member_of"
    LEADER_OF = "leader_of"
    ALLIED_WITH = "allied_with"
    ENEMY_OF = "enemy_of"
    LOCATED_IN = "located_in"
    POSSESSES = "possesses"
    CREATED_BY = "created_by"
    PARTICIPATED_IN = "participated_in"
    CAUSE_OF = "cause_of"


@dataclass(frozen=True)
class TimelinePoint:
    year: int
    era: str

    def __str__(self) -> str:
        return f"Year {self.year} ({self.era})"


@dataclass(frozen=True)
class EntityRelation:
    target_entity_name: str
    relation_type: RelationType
    context: Optional[str] = None


@dataclass(frozen=True)
class ResourceLimitConfig:
    max_memory_mb: int = 512
    cpu_cap_percent: int = 80
    auto_trim_idle: bool = True
