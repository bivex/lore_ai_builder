from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from ...domain.model.value_objects import EntityType


@dataclass(frozen=True)
class WorkflowTaskDTO:
    """Represents a single task defined in a YAML workflow specification."""
    task_type: str  # "generate", "swarm", "audit", "classify", "temporal", "score", "graph", "show_world"
    name: Optional[str] = None
    entity_type: Optional[EntityType] = None
    prompt: Optional[str] = None
    narrative: Optional[str] = None
    era: str = "First Age"
    year: int = 100
    source: Optional[str] = None
    target: Optional[str] = None
    context: Optional[str] = None
    interval_a: Optional[str] = None
    interval_b: Optional[str] = None
    candidate_relations: Optional[List[str]] = None
    raw_config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldConfigDTO:
    """Optional World Bible definition configured via YAML."""
    name: str = "Aethelgard"
    cosmology: str = "A fractured plane orbiting a dying stellar core, bound by the Ley Lines."
    immutable_laws: List[str] = field(default_factory=lambda: [
        "Magic demands an equal sacrifice of vitality (No free energy)",
        "Mortals cannot achieve true divinity without burning their mortal shell",
        "The Void Rifts cannot be sealed, only diverted",
    ])
    tone: str = "mythic_fantasy"


@dataclass(frozen=True)
class WorkflowSettingsDTO:
    """Runtime execution settings configured via YAML."""
    use_mock_llm: bool = False
    use_tencent_memory: bool = False
    output_file: Optional[str] = None
    memory_file: Optional[str] = None
    log_level: str = "INFO"


@dataclass(frozen=True)
class WorkflowConfigDTO:
    """Root model representing a parsed YAML task specification file."""
    version: str
    settings: WorkflowSettingsDTO
    tasks: List[WorkflowTaskDTO]
    world: Optional[WorldConfigDTO] = None


@dataclass
class WorkflowExecutionResultDTO:
    """Overall outcome after executing all YAML tasks."""
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    task_results: List[Dict[str, Any]] = field(default_factory=list)
    output_file_written: Optional[str] = None
    memory_file_written: Optional[str] = None
