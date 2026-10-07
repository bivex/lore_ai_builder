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


def test_russian_yaml_workflow_execution():
    """Validates full execution of Russian declarative YAML configuration with dark Slavic fantasy lore."""
    config_path = "configs/tasks_ru.yml"
    assert os.path.exists(config_path), "configs/tasks_ru.yml should exist"

    workflow = YamlWorkflowParser.parse_file(config_path)
    assert workflow.world.name == "Северное Порубежье: Явь и Навь"
    assert len(workflow.world.immutable_laws) == 3
    assert len(workflow.tasks) == 8

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
    assert res.total_tasks == 8
    assert res.successful_tasks == 8
    assert res.failed_tasks == 0

    # Task 1: Generate
    t1 = res.task_results[0]["result"]
    assert t1["entity_name"] == "Воевода Радомир"
    assert t1["status"] == "canonical"

    # Task 3: Audit valid (metaphorical undying loyalty)
    t3 = res.task_results[2]["result"]
    assert t3["verdict"] == "APPROVE"
    assert t3["p_compliant"] > 0.9

    # Task 4: Audit violating (immortal tyrant infinite magic)
    t4 = res.task_results[3]["result"]
    assert t4["verdict"] == "REJECT_AXIOM_VIOLATION"
    assert t4["p_compliant"] < 0.1

    # Task 5: Classify relation
    t5 = res.task_results[4]["result"]
    assert t5["chosen_relation"] == "ruler_of"

    # Task 6: Temporal
    t6 = res.task_results[5]["result"]
    assert t6["allen_relation"] == "before"

    # Memory JSON Dump Verification
    assert res.memory_file_written is not None
    assert os.path.exists(res.memory_file_written)
    with open(res.memory_file_written, "r", encoding="utf-8") as f:
        mem_dump = json.load(f)
        assert "l3_core" in mem_dump
        assert "l1_atomic_facts" in mem_dump
        assert "l0_conversations" in mem_dump
        assert "knowledge_wiki_graph" in mem_dump
        assert mem_dump["l3_core"]["name"] == "Северное Порубежье: Явь и Навь"
        assert len(mem_dump["l1_atomic_facts"]) >= 10


def test_l0_to_l3_memory_json_serialization_and_rehydration():
    """Validates full serialization of L0-L3 memory tiers to JSON and rehydration into memory."""
    memory = InMemoryLoreMemoryAdapter()
    from lore_builder.domain.model.entity import LoreFact
    from lore_builder.domain.model.aggregate import WorldBibleAggregate

    custom_bible = WorldBibleAggregate(
        world_id="w_test",
        name="Test Dimension",
        cosmology="A pocket realm of light",
        immutable_laws=["Shadow cannot dwell here"],
        tone="ethereal",
    )
    memory.save_world_bible(custom_bible)
    memory.commit_atomic_fact(LoreFact(fact_id="f1", entity_name="Solar Avatar", statement="The sun never sets."))
    memory.save_draft_conversation("sess_1", "Generate sun", "Sun generated")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp_json = tf.name

    try:
        saved_path = memory.dump_to_json(tmp_json)
        assert saved_path == tmp_json
        assert os.path.exists(tmp_json)

        new_memory = InMemoryLoreMemoryAdapter()
        new_memory.load_from_json(tmp_json)

        bible = new_memory.get_world_bible()
        assert bible.name == "Test Dimension"
        assert bible.immutable_laws == ["Shadow cannot dwell here"]

        facts = new_memory.search_canonical_facts("Solar")
        assert len(facts) == 1
        assert facts[0].statement == "The sun never sets."
    finally:
        if os.path.exists(tmp_json):
            os.remove(tmp_json)

