import os
import json
import pytest
import tempfile

from lore_builder.application.services.yaml_workflow_service import YamlWorkflowParser
from lore_builder.application.use_cases.execute_workflow_use_case import ExecuteWorkflowUseCase
from lore_builder.application.use_cases.generate_entity_use_case import GenerateEntityUseCase
from lore_builder.application.use_cases.orchestrate_swarm_use_case import OrchestrateSwarmUseCase
from lore_builder.application.use_cases.audit_entity_use_case import AuditEntityUseCase
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
from lore_builder.infrastructure.adapters.llm.mock_llm_adapter import MockLLMAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter
from lore_builder.infrastructure.adapters.audit.open_jev_lore_adapter import OpenJevLoreAdapter


def test_parse_valid_yaml_config():
    yaml_text = """
version: "1.0"
world:
  name: "Valoria"
  cosmology: "A celestial realm of crystal"
  immutable_laws:
    - "No shadow may pierce the crystal core"
settings:
  use_mock_llm: true
  output_file: "output/valoria.json"
tasks:
  - type: generate
    name: "Sun Champion"
    entity_type: character
    prompt: "A solar knight wielding dawn magic"
  - type: audit
    name: "Dark Infiltrator"
    narrative: "An undying shadow that pierced the crystal core without cost"
"""
    config = YamlWorkflowParser.parse_yaml(yaml_text)
    assert config.version == "1.0"
    assert config.world is not None
    assert config.world.name == "Valoria"
    assert config.settings.use_mock_llm is True
    assert len(config.tasks) == 2
    assert config.tasks[0].task_type == "generate"
    assert config.tasks[0].name == "Sun Champion"
    assert config.tasks[1].task_type == "audit"


def test_parse_yaml_missing_tasks_raises_error():
    yaml_text = """
version: "1.0"
settings:
  use_mock_llm: true
"""
    with pytest.raises(ValueError, match="must define a non-empty 'tasks' list"):
        YamlWorkflowParser.parse_yaml(yaml_text)


def test_parse_yaml_invalid_task_type_raises_error():
    yaml_text = """
tasks:
  - type: unknown_task_type
    name: "Nobody"
"""
    with pytest.raises(ValueError, match="invalid or missing 'type'"):
        YamlWorkflowParser.parse_yaml(yaml_text)


def test_execute_workflow_use_case_end_to_end():
    yaml_text = """
version: "1.0"
settings:
  use_mock_llm: true
tasks:
  - type: generate
    name: "Aethelgard Knight"
    entity_type: character
    prompt: "A valiant defender"
  - type: audit
    name: "Malakor"
    narrative: "Became immortal and cast infinite magic without sacrifice"
  - type: classify
    source: "Commander"
    target: "Legion"
    context: "Commander leads and directs the Legion"
"""
    workflow = YamlWorkflowParser.parse_yaml(yaml_text)

    memory = InMemoryLoreMemoryAdapter()
    resources = JobObjectsResourceAdapter()
    events = InMemoryEventPublisherAdapter()
    llm = MockLLMAdapter(should_violate_canon=False)
    jev = OpenJevLoreAdapter()

    auditor = AuditEntityUseCase(memory_port=memory, event_publisher=events, jev_port=jev)
    generator = GenerateEntityUseCase(
        memory_port=memory,
        resource_controller=resources,
        llm_provider=llm,
        event_publisher=events,
        audit_use_case=auditor,
    )
    orchestrator = OrchestrateSwarmUseCase(
        memory_port=memory,
        resource_controller=resources,
        llm_provider=llm,
        event_publisher=events,
        jev_port=jev,
        audit_use_case=auditor,
    )

    executor = ExecuteWorkflowUseCase(
        memory_port=memory,
        generator=generator,
        orchestrator=orchestrator,
        auditor=auditor,
        jev_port=jev,
    )

    res = executor.execute(workflow)
    assert res.total_tasks == 3
    assert res.successful_tasks == 3
    assert res.failed_tasks == 0
    assert len(res.task_results) == 3

    # Check task 1 (generate)
    assert res.task_results[0]["result"]["entity_name"] == "Aethelgard Knight"

    # Check task 2 (audit)
    assert res.task_results[1]["result"]["verdict"] == "REJECT_AXIOM_VIOLATION"

    # Check task 3 (classify)
    assert res.task_results[2]["result"]["chosen_relation"] == "ruler_of"


def test_workflow_output_file_generation():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        yaml_text = f"""
version: "1.0"
settings:
  use_mock_llm: true
  output_file: "{tmp_path}"
tasks:
  - type: score
    narrative: "An ordinary farmer plowing wheat fields in the morning"
"""
        workflow = YamlWorkflowParser.parse_yaml(yaml_text)

        memory = InMemoryLoreMemoryAdapter()
        resources = JobObjectsResourceAdapter()
        events = InMemoryEventPublisherAdapter()
        llm = MockLLMAdapter(should_violate_canon=False)
        jev = OpenJevLoreAdapter()

        auditor = AuditEntityUseCase(memory_port=memory, event_publisher=events, jev_port=jev)
        generator = GenerateEntityUseCase(
            memory_port=memory,
            resource_controller=resources,
            llm_provider=llm,
            event_publisher=events,
            audit_use_case=auditor,
        )
        orchestrator = OrchestrateSwarmUseCase(
            memory_port=memory,
            resource_controller=resources,
            llm_provider=llm,
            event_publisher=events,
            jev_port=jev,
            audit_use_case=auditor,
        )

        executor = ExecuteWorkflowUseCase(
            memory_port=memory,
            generator=generator,
            orchestrator=orchestrator,
            auditor=auditor,
            jev_port=jev,
        )

        res = executor.execute(workflow)
        assert res.output_file_written == tmp_path
        assert os.path.exists(tmp_path)

        with open(tmp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["task_type"] == "score"
            assert data[0]["status"] == "SUCCESS"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
