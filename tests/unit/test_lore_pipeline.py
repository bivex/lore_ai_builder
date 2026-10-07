import pytest
import os

from lore_builder.domain.model.value_objects import EntityType, CanonStatus, RelationType, TimelinePoint
from lore_builder.domain.model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from lore_builder.domain.services.consistency_checker import DomainConsistencyPolicy
from lore_builder.domain.exceptions import LoreCanonConflictError

from lore_builder.application.dto.entity_dto import GenerateEntityCommand
from lore_builder.application.use_cases.audit_entity_use_case import AuditEntityUseCase
from lore_builder.application.use_cases.generate_entity_use_case import GenerateEntityUseCase

from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.llm.mock_llm_adapter import MockLLMAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter


def test_domain_entity_lifecycle():
    entity = LoreEntityAggregate.create_draft(
        name="Aethelgard Watch",
        entity_type=EntityType.FACTION,
        summary="Guardians of the veil",
        description="A fortress order.",
    )
    assert entity.status == CanonStatus.DRAFT
    assert len(entity.pull_events()) == 1

    entity.request_audit()
    assert entity.status == CanonStatus.AUDITING

    entity.mark_canonical(auditor_notes="Fully compliant with First Age canon.")
    assert entity.status == CanonStatus.CANONICAL


def test_consistency_policy_detects_violation():
    world_bible = WorldBibleAggregate(
        world_id="w1",
        name="TestWorld",
        cosmology="Dark Realm",
        immutable_laws=["Mortals must remain mortal (No immortality)"],
    )

    entity = LoreEntityAggregate.create_draft(
        name="Vampire Lord",
        entity_type=EntityType.CHARACTER,
        summary="An undying creature",
        description="Became immortal through dark ritual.",
    )

    report = DomainConsistencyPolicy.audit_entity(entity, world_bible, [])
    assert not report.is_valid
    assert any("mortality rule" in c.lower() for c in report.contradictions)


def test_end_to_end_generation_with_job_objects_shield():
    memory = InMemoryLoreMemoryAdapter()
    resources = JobObjectsResourceAdapter()
    events = InMemoryEventPublisherAdapter()
    llm = MockLLMAdapter(should_violate_canon=False)

    auditor = AuditEntityUseCase(memory_port=memory, event_publisher=events)
    generator = GenerateEntityUseCase(
        memory_port=memory,
        resource_controller=resources,
        llm_provider=llm,
        event_publisher=events,
        audit_use_case=auditor,
    )

    cmd = GenerateEntityCommand(
        name="Kaelen Voss",
        entity_type=EntityType.CHARACTER,
        prompt_hint="Commander of the Silver Wardens",
        era="First Age",
        year=245,
    )

    result = generator.execute(cmd)

    assert result.name == "Kaelen Voss"
    assert result.status == CanonStatus.CANONICAL.value
    assert len(result.facts) >= 1
    assert len(result.relations) >= 1

    # Verify L1 Memory persistence
    search_results = memory.search_canonical_facts("Kaelen")
    assert len(search_results) >= 1
    assert "Kaelen Voss" in search_results[0].statement

    # Verify Wiki Link Graph
    wiki_graph = memory.get_entity_wiki_graph("Kaelen Voss")
    assert wiki_graph["node"] == "Kaelen Voss"
    assert "Silver Wardens" in wiki_graph["outbound_links"]


def test_canon_violation_triggers_rejection():
    memory = InMemoryLoreMemoryAdapter()
    resources = JobObjectsResourceAdapter()
    events = InMemoryEventPublisherAdapter()
    # Configure mock LLM to intentionally violate canon
    llm = MockLLMAdapter(should_violate_canon=True)

    auditor = AuditEntityUseCase(memory_port=memory, event_publisher=events)
    generator = GenerateEntityUseCase(
        memory_port=memory,
        resource_controller=resources,
        llm_provider=llm,
        event_publisher=events,
        audit_use_case=auditor,
    )

    cmd = GenerateEntityCommand(
        name="Malakor the Defiant",
        entity_type=EntityType.CHARACTER,
        prompt_hint="Defied mortal laws",
    )

    with pytest.raises(LoreCanonConflictError) as exc_info:
        generator.execute(cmd)

    assert "Malakor the Defiant" in str(exc_info.value)
