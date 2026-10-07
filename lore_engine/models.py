from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class EntityType(str, Enum):
    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    HISTORICAL_EVENT = "historical_event"
    ARTIFACT = "artifact"


class Relation(BaseModel):
    target: str = Field(description="Name of the referenced entity")
    type: str = Field(description="Ontological relation type: leader_of, allied_with, enemy_of, located_in, participated_in, cause_of, possesses, member_of")
    context: str = Field(default="", description="Narrative context describing why this relationship exists")


class Entity(BaseModel):
    name: str
    entity_type: EntityType
    summary: str
    description: str
    era: str = "Первая Эпоха"
    year: int = 100
    facts: List[str] = Field(default_factory=list, description="Atomic verified facts about this entity")
    relations: List[Relation] = Field(default_factory=list, description="Direct ontological connections to other entities")


class Task(BaseModel):
    name: str
    entity_type: Optional[EntityType] = None
    hint: str = ""
    source_entity: Optional[str] = None
    depth: int = 0
    priority: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed


class WorldBible(BaseModel):
    name: str = "Северное Порубежье: Явь и Навь"
    cosmology: str = "Расколотый мир на границе ледяной Яви и потусторонней Нави, сдерживаемый древними рунными заставами."
    immutable_laws: List[str] = Field(default_factory=lambda: [
        "Магия требует эквивалентной жертвы жизненной силы (закон сохранения чар)",
        "Смертные не могут обрести истинное бессмертие или стать богами",
        "Врата Нави не могут быть запечатаны навсегда, их можно лишь сдерживать",
    ])
    tone: str = "dark_slavic_fantasy"
