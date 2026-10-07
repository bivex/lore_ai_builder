import os
import yaml
from typing import Dict, Any, List

from ..dto.workflow_dto import (
    WorkflowConfigDTO,
    WorkflowSettingsDTO,
    WorkflowTaskDTO,
    WorldConfigDTO,
)
from ...domain.model.value_objects import EntityType


class YamlWorkflowParser:
    """Service responsible for loading, parsing, and strictly validating YAML task specifications."""

    VALID_TASK_TYPES = {
        "generate", "entity",
        "swarm",
        "audit", "jev-audit", "jev_audit",
        "classify", "jev-classify", "jev_classify",
        "temporal", "jev-temporal", "jev_temporal",
        "score", "jev-score", "jev_score",
        "graph",
        "show-world", "show_world",
    }

    @classmethod
    def load_from_file(cls, file_path: str) -> WorkflowConfigDTO:
        """Loads and parses a workflow configuration from a YAML file path."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"YAML task specification file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise IOError(f"Could not read YAML task file '{file_path}': {e}")

        return cls.parse_yaml(content, source_name=file_path)

    @classmethod
    def parse_yaml(cls, yaml_content: str, source_name: str = "<string>") -> WorkflowConfigDTO:
        """Parses a YAML string into a strictly validated WorkflowConfigDTO."""
        if not yaml_content or not yaml_content.strip():
            raise ValueError(f"YAML workflow specification in {source_name} is empty.")

        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ValueError(f"Syntax error in YAML workflow specification ({source_name}): {e}")

        if not isinstance(data, dict):
            raise ValueError(f"Root of YAML specification in {source_name} must be a dictionary/mapping.")

        version = str(data.get("version", "1.0"))

        # 1. Parse Settings
        raw_settings = data.get("settings", {})
        if not isinstance(raw_settings, dict):
            raise ValueError(f"'settings' in {source_name} must be a dictionary.")

        settings = WorkflowSettingsDTO(
            use_mock_llm=bool(raw_settings.get("use_mock_llm", False)),
            use_tencent_memory=bool(raw_settings.get("use_tencent_memory", False)),
            output_file=raw_settings.get("output_file"),
            log_level=str(raw_settings.get("log_level", "INFO")).upper(),
        )

        # 2. Parse World Bible (Optional)
        raw_world = data.get("world")
        world_dto = None
        if raw_world:
            if not isinstance(raw_world, dict):
                raise ValueError(f"'world' in {source_name} must be a dictionary.")
            laws = raw_world.get("immutable_laws")
            if laws is not None and not isinstance(laws, list):
                raise ValueError(f"'immutable_laws' in world config must be a list of strings.")
            world_dto = WorldConfigDTO(
                name=raw_world.get("name", "Aethelgard"),
                cosmology=raw_world.get("cosmology", "A fractured plane orbiting a dying core"),
                immutable_laws=laws if laws else [
                    "Magic demands an equal sacrifice of vitality (No free energy)",
                    "Mortals cannot achieve true divinity without burning their mortal shell",
                    "The Void Rifts cannot be sealed, only diverted",
                ],
                tone=raw_world.get("tone", "mythic_fantasy"),
            )

        # 3. Parse Tasks
        raw_tasks = data.get("tasks")
        if not raw_tasks:
            raise ValueError(f"YAML specification in {source_name} must define a non-empty 'tasks' list.")
        if not isinstance(raw_tasks, list):
            raise ValueError(f"'tasks' in {source_name} must be a list of task specifications.")

        tasks: List[WorkflowTaskDTO] = []
        for idx, t in enumerate(raw_tasks):
            if not isinstance(t, dict):
                raise ValueError(f"Task #{idx + 1} in {source_name} must be a dictionary.")

            raw_type = str(t.get("type", "")).strip().lower()
            if not raw_type or raw_type not in cls.VALID_TASK_TYPES:
                raise ValueError(
                    f"Task #{idx + 1} has invalid or missing 'type': '{raw_type}'. "
                    f"Allowed types: {sorted(list(cls.VALID_TASK_TYPES))}"
                )

            # Normalize canonical task type
            canonical_type = raw_type
            if canonical_type == "entity":
                canonical_type = "generate"
            elif canonical_type in ("jev-audit", "jev_audit"):
                canonical_type = "audit"
            elif canonical_type in ("jev-classify", "jev_classify"):
                canonical_type = "classify"
            elif canonical_type in ("jev-temporal", "jev_temporal"):
                canonical_type = "temporal"
            elif canonical_type in ("jev-score", "jev_score"):
                canonical_type = "score"
            elif canonical_type == "show_world":
                canonical_type = "show-world"

            # Strict field validation per type
            task_dto = cls._build_task_dto(canonical_type, t, idx, source_name)
            tasks.append(task_dto)

        return WorkflowConfigDTO(
            version=version,
            settings=settings,
            tasks=tasks,
            world=world_dto,
        )

    @classmethod
    def _build_task_dto(cls, task_type: str, d: Dict[str, Any], idx: int, source: str) -> WorkflowTaskDTO:
        prefix = f"Task #{idx + 1} ({task_type}) in {source}"

        if task_type == "generate":
            name = d.get("name")
            if not name or not str(name).strip():
                raise ValueError(f"{prefix} requires a non-empty 'name'.")
            prompt = d.get("prompt") or d.get("hint")
            if not prompt or not str(prompt).strip():
                raise ValueError(f"{prefix} requires a non-empty 'prompt' or 'hint'.")
            raw_etype = str(d.get("entity_type", "character")).lower()
            try:
                entity_type = EntityType(raw_etype)
            except ValueError:
                raise ValueError(f"{prefix} has invalid 'entity_type': '{raw_etype}'. Allowed: {[e.value for e in EntityType]}")
            return WorkflowTaskDTO(
                task_type="generate",
                name=str(name).strip(),
                entity_type=entity_type,
                prompt=str(prompt).strip(),
                era=str(d.get("era", "First Age")),
                year=int(d.get("year", 100)),
                raw_config=d,
            )

        elif task_type == "swarm":
            prompt = d.get("prompt")
            if not prompt or not str(prompt).strip():
                raise ValueError(f"{prefix} requires a non-empty 'prompt'.")
            return WorkflowTaskDTO(
                task_type="swarm",
                prompt=str(prompt).strip(),
                raw_config=d,
            )

        elif task_type == "audit":
            name = d.get("name")
            if not name or not str(name).strip():
                raise ValueError(f"{prefix} requires a non-empty 'name'.")
            narrative = d.get("narrative") or d.get("text")
            if not narrative or not str(narrative).strip():
                raise ValueError(f"{prefix} requires a non-empty 'narrative' or 'text'.")
            return WorkflowTaskDTO(
                task_type="audit",
                name=str(name).strip(),
                narrative=str(narrative).strip(),
                raw_config=d,
            )

        elif task_type == "classify":
            source_ent = d.get("source") or d.get("entity_a")
            target_ent = d.get("target") or d.get("entity_b")
            context = d.get("context") or d.get("narrative")
            if not source_ent or not str(source_ent).strip():
                raise ValueError(f"{prefix} requires 'source' (or 'entity_a').")
            if not target_ent or not str(target_ent).strip():
                raise ValueError(f"{prefix} requires 'target' (or 'entity_b').")
            if not context or not str(context).strip():
                raise ValueError(f"{prefix} requires 'context'.")
            candidates = d.get("candidate_relations")
            if candidates and not isinstance(candidates, list):
                raise ValueError(f"{prefix} 'candidate_relations' must be a list of strings if provided.")
            return WorkflowTaskDTO(
                task_type="classify",
                source=str(source_ent).strip(),
                target=str(target_ent).strip(),
                context=str(context).strip(),
                candidate_relations=[str(c) for c in candidates] if candidates else None,
                raw_config=d,
            )

        elif task_type == "temporal":
            ia = d.get("interval_a") or d.get("a")
            ib = d.get("interval_b") or d.get("b")
            context = d.get("context")
            if not ia or not str(ia).strip():
                raise ValueError(f"{prefix} requires 'interval_a' (or 'a').")
            if not ib or not str(ib).strip():
                raise ValueError(f"{prefix} requires 'interval_b' (or 'b').")
            if not context or not str(context).strip():
                raise ValueError(f"{prefix} requires 'context'.")
            return WorkflowTaskDTO(
                task_type="temporal",
                interval_a=str(ia).strip(),
                interval_b=str(ib).strip(),
                context=str(context).strip(),
                raw_config=d,
            )

        elif task_type == "score":
            narrative = d.get("narrative") or d.get("text")
            if not narrative or not str(narrative).strip():
                raise ValueError(f"{prefix} requires 'narrative' or 'text'.")
            return WorkflowTaskDTO(
                task_type="score",
                narrative=str(narrative).strip(),
                raw_config=d,
            )

        elif task_type == "graph":
            name = d.get("name")
            if not name or not str(name).strip():
                raise ValueError(f"{prefix} requires 'name'.")
            return WorkflowTaskDTO(
                task_type="graph",
                name=str(name).strip(),
                raw_config=d,
            )

        elif task_type == "show-world":
            return WorkflowTaskDTO(
                task_type="show-world",
                raw_config=d,
            )

        raise ValueError(f"Unhandled task type '{task_type}'")
