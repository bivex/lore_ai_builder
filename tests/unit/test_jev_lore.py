import pytest

from lore_builder.domain.model.value_objects import EntityType, CanonStatus
from lore_builder.domain.model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from lore_builder.domain.model.jev_decisions import (
    JevNoulDecision,
    JevChoiceDecision,
    JevScoreDecision,
)
from lore_builder.application.use_cases.audit_entity_use_case import AuditEntityUseCase
from lore_builder.infrastructure.adapters.audit.open_jev_lore_adapter import OpenJevLoreAdapter
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter


def test_jev_noul_axiom_evaluation():
    jev = OpenJevLoreAdapter()
    world_rule = "Magic demands an equal sacrifice of vitality (No free energy)"

    # Compliant entity
    comp = jev.evaluate_axiom_compliance(
        world_rules=world_rule,
        entity_narrative="Kaelen sacrificed half his life essence to seal the rift.",
        specific_rule=world_rule,
    )
    assert comp.verdict is True
    assert comp.p_yes >= 0.8
    assert comp.confidence >= 0.8

    # Violating entity
    viol = jev.evaluate_axiom_compliance(
        world_rules=world_rule,
        entity_narrative="Malakor cast infinite magic without cost or sacrifice.",
        specific_rule=world_rule,
    )
    assert viol.verdict is False
    assert viol.p_yes <= 0.2


def test_jev_score_distortion_risk():
    jev = OpenJevLoreAdapter()

    # Low risk
    safe_score = jev.evaluate_lore_distortion_risk(
        world_context="High fantasy realm",
        entity_narrative="An ordinary blacksmith who crafts iron armor for knights.",
    )
    assert safe_score.score < 1.0

    # High distortion risk
    high_score = jev.evaluate_lore_distortion_risk(
        world_context="High fantasy realm",
        entity_narrative="An undying sorcerer wielding infinite magic without cost.",
    )
    assert high_score.score >= 2.0
    assert high_score.level_probabilities["canon_breaking"] >= 0.5


def test_jev_choice_relation_classification():
    jev = OpenJevLoreAdapter()
    candidates = ["leader_of", "allied_with", "enemy_of", "located_in"]

    dec = jev.classify_relation_type(
        entity_a="General Voss",
        entity_b="The Silver Legion",
        narrative_context="General Voss commands the Silver Legion with strict discipline.",
        candidate_relations=candidates,
    )
    assert dec.chosen_option == "leader_of"
    assert dec.probabilities["leader_of"] > 0.4


def test_audit_entity_with_jev_interception():
    memory = InMemoryLoreMemoryAdapter()
    events = InMemoryEventPublisherAdapter()
    jev = OpenJevLoreAdapter()

    auditor = AuditEntityUseCase(
        memory_port=memory,
        event_publisher=events,
        jev_port=jev,
    )

    # Valid entity
    valid_entity = LoreEntityAggregate.create_draft(
        name="Brother Alden",
        entity_type=EntityType.CHARACTER,
        summary="A monk who surrendered his speech in sacred vow",
        description="He sacrificed his voice in the Temple of Dawn.",
    )
    res_valid = auditor.execute(valid_entity)
    assert res_valid.is_valid is True
    assert valid_entity.status == CanonStatus.CANONICAL

    # Invalid entity
    invalid_entity = LoreEntityAggregate.create_draft(
        name="The Undying Defier",
        entity_type=EntityType.CHARACTER,
        summary="An immortal tyrant",
        description="Became immortal and cast infinite spells without sacrifice.",
    )
    res_invalid = auditor.execute(invalid_entity)
    assert res_invalid.is_valid is False
    assert invalid_entity.status == CanonStatus.REJECTED
    assert any("JEV DECISION ENGINE" in c for c in res_invalid.contradictions)


def test_jev_batch_lore_axioms():
    jev = OpenJevLoreAdapter()
    axioms = [
        "Magic demands an equal sacrifice of vitality (No free energy)",
        "Mortals cannot achieve true divinity without burning their mortal shell",
        "The Void Rifts cannot be sealed, only diverted",
    ]
    narrative = "Lord Vael sacrificed ten lifespans to divert the void rift from Eldoria."

    results = jev.batch_decide_lore_axioms(
        world_rules="World Rules Context",
        entity_narrative=narrative,
        axioms=axioms,
    )

    assert len(results) == 3
    for axiom, decision in results.items():
        assert decision.verdict is True
        assert decision.p_yes >= 0.7


def test_jev_temporal_allen_relation_classification():
    jev = OpenJevLoreAdapter()

    # Before test
    res_before = jev.classify_temporal_relation(
        interval_a="The Primordial Dawn",
        interval_b="The Age of Iron",
        narrative_context="The Primordial Dawn preceded and was prior to the Age of Iron.",
    )
    assert res_before.allen_relation == "before"
    assert res_before.confidence >= 0.5

    # During test
    res_during = jev.classify_temporal_relation(
        interval_a="Reign of King Aldous",
        interval_b="The Great Plague",
        narrative_context="The Great Plague occurred during and amidst the reign of King Aldous.",
    )
    assert res_during.allen_relation == "during"
    assert res_during.confidence >= 0.5


def test_swarm_orchestration_with_jev_integration():
    from lore_builder.application.use_cases.orchestrate_swarm_use_case import OrchestrateSwarmUseCase
    from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
    from lore_builder.infrastructure.adapters.llm.mock_llm_adapter import MockLLMAdapter

    memory = InMemoryLoreMemoryAdapter()
    resources = JobObjectsResourceAdapter()
    events = InMemoryEventPublisherAdapter()
    llm = MockLLMAdapter(should_violate_canon=False)
    jev = OpenJevLoreAdapter()

    orchestrator = OrchestrateSwarmUseCase(
        memory_port=memory,
        resource_controller=resources,
        llm_provider=llm,
        event_publisher=events,
        jev_port=jev,
    )

    result = orchestrator.execute("Generate high commander Kaelen and the Silver Wardens legion")
    assert result.total_waves >= 1
    assert len(result.entities_generated) >= 1
    assert result.facts_committed >= 1

