from enum import Enum
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class Violation(BaseModel):
    axiom: str = Field(description="Дословно закон из аксиом мира, который нарушен")
    quote: str = Field(description="Точная цитата из текста сущности, где найдено нарушение")
    explanation: str = Field(default="", description="Почему это нарушает закон")
    severity: Literal["minor", "severe", "canon_breaking"] = "canon_breaking"


class Verdict(BaseModel):
    is_valid: bool = Field(default=True, description="Является ли сущность канонически верной")
    violations: List[Violation] = Field(default_factory=list, description="Список выявленных нарушений")
    needs_review: bool = Field(default=False, description="Флаг для спорных случаев, не останавливающий прогон")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class EntityType(str, Enum):
    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    HISTORICAL_EVENT = "historical_event"
    ARTIFACT = "artifact"


class RelationType(str, Enum):
    LEADER_OF = "leader_of"
    MEMBER_OF = "member_of"
    PREDECESSOR_OF = "predecessor_of"
    SUCCESSOR_OF = "successor_of"
    ALLIED_WITH = "allied_with"
    ENEMY_OF = "enemy_of"
    LOCATED_IN = "located_in"
    PARTICIPATED_IN = "participated_in"
    POSSESSES = "possesses"
    CREATED_BY = "created_by"
    ADJACENT_TO = "adjacent_to"
    CAUSE_OF = "cause_of"


class Relation(BaseModel):
    target: str = Field(description="Name of the referenced entity")
    type: str = Field(
        description="Ontological relation type: leader_of, predecessor_of, successor_of, member_of, allied_with, enemy_of, located_in, participated_in, cause_of, possesses, created_by, adjacent_to"
    )
    context: str = Field(default="", description="Narrative context describing why this relationship exists")


class ProseVerification(BaseModel):
    is_supported: bool = Field(default=True, description="Опирается ли художественный текст строго на утвержденные факты")
    unsupported_claims: List[str] = Field(default_factory=list, description="Утверждения в прозе, которых нет в утвержденных фактах")
    style_issues: List[str] = Field(default_factory=list, description="Анахронизмы (шестеренки, часовые механизмы) или выдуманные слова")


class AtomicFact(BaseModel):
    year: int = Field(description="Точный год события")
    era: str = Field(default="Вторая Эпоха", description="Эпоха (Первая Эпоха, Вторая Эпоха)")
    statement: str = Field(description="Атомарное проверяемое утверждение")
    participants: List[str] = Field(default_factory=list, description="Имена сущностей, упоминаемых в факте")


class EntityFactsDraft(BaseModel):
    name: str
    entity_type: EntityType
    era: str = "Вторая Эпоха"
    year: int = 100
    facts: List[AtomicFact] = Field(default_factory=list, description="3-4 атомарных проверяемых факта")
    relations: List[Relation] = Field(default_factory=list, description="Прямые онтологические связи")


class Entity(BaseModel):
    name: str
    entity_type: EntityType
    summary: str
    description: str
    era: str = "Вторая Эпоха"
    year: int = 100
    facts: List[str] = Field(default_factory=list, description="Atomic verified facts about this entity")
    atomic_facts: List[AtomicFact] = Field(default_factory=list, description="Structured verified atomic facts with year and participants")
    relations: List[Relation] = Field(default_factory=list, description="Direct ontological connections to other entities")
    audit_status: str = Field(default="canonical", description="Verification status: canonical, needs_review, rejected")
    audit_issues: List[str] = Field(default_factory=list, description="Unresolved audit issues or warnings")
    audit_verdict: Optional[Verdict] = None
    audit_notes: List[str] = Field(default_factory=list)


class Task(BaseModel):
    name: str
    entity_type: Optional[EntityType] = None
    hint: str = ""
    source_entity: Optional[str] = None
    depth: int = 0
    priority: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed
    retry_count: int = Field(default=0, description="Execution attempts counter")
    error_message: Optional[str] = Field(default=None, description="Last failure reason")


class WorldBible(BaseModel):
    name: str = "Северное Порубежье: Явь и Навь"
    cosmology: str = "Расколотый мир на границе ледяной Яви и потусторонней Нави, сдерживаемый древними рунными заставами."
    eras: List[str] = Field(default_factory=lambda: [
        "Эпоха Первородных Лесов",
        "Первая Эпоха",
        "Вторая Эпоха",
        "Эпоха Застав",
    ], description="Канонические эпохи вселенной")
    immutable_laws: List[str] = Field(default_factory=lambda: [
        "Магия требует эквивалентной жертвы жизненной силы (закон сохранения чар)",
        "Смертные не могут обрести истинное бессмертие или стать богами",
        "Врата Нави не могут быть запечатаны навсегда, их можно лишь сдерживать",
    ])
    tone: str = "dark_slavic_fantasy"
