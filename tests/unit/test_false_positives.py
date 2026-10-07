import pytest

from lore_builder.domain.model.value_objects import EntityType, CanonStatus, TimelinePoint
from lore_builder.domain.model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from lore_builder.domain.model.entity import LoreFact
from lore_builder.domain.services.consistency_checker import DomainConsistencyPolicy
from lore_builder.domain.services.entity_resolver import EntityResolutionService
from lore_builder.infrastructure.adapters.audit.open_jev_lore_adapter import OpenJevLoreAdapter
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter
from lore_builder.application.use_cases.audit_entity_use_case import AuditEntityUseCase


@pytest.fixture
def world_bible():
    return WorldBibleAggregate(
        world_id="w1",
        name="Aethelgard",
        cosmology="A fractured plane orbiting a dying core",
        immutable_laws=[
            "Magic demands an equal sacrifice of vitality (No free energy)",
            "Mortals cannot achieve true divinity without burning their mortal shell",
            "The Void Rifts cannot be sealed, only diverted",
        ],
    )


def test_false_positive_undying_loyalty(world_bible):
    """Metaphorical 'undying loyalty' must not be flagged as an immortality violation."""
    entity = LoreEntityAggregate.create_draft(
        name="Sir Gareth",
        entity_type=EntityType.CHARACTER,
        summary="A mortal knight of the realm",
        description="Sir Gareth swore undying loyalty to the High King and sacrificed his shield arm in defense of the realm.",
    )
    jev = OpenJevLoreAdapter()
    auditor = AuditEntityUseCase(
        memory_port=InMemoryLoreMemoryAdapter(),
        event_publisher=InMemoryEventPublisherAdapter(),
        jev_port=jev,
    )
    res = auditor.execute(entity)
    assert res.is_valid is True, f"False positive detected: {res.contradictions}"


def test_false_positive_immortal_legacy(world_bible):
    """Metaphorical 'immortal legacy' must not be flagged as an immortality violation."""
    entity = LoreEntityAggregate.create_draft(
        name="Master Elian",
        entity_type=EntityType.CHARACTER,
        summary="A mortal poet and philosopher",
        description="He lived for sixty years and left behind an immortal legacy of philosophy and verse.",
    )
    jev = OpenJevLoreAdapter()
    auditor = AuditEntityUseCase(
        memory_port=InMemoryLoreMemoryAdapter(),
        event_publisher=InMemoryEventPublisherAdapter(),
        jev_port=jev,
    )
    res = auditor.execute(entity)
    assert res.is_valid is True, f"False positive detected: {res.contradictions}"


def test_false_positive_fighting_immortal_foe(world_bible):
    """Fighting against an immortal monster must not flag the mortal hero."""
    entity = LoreEntityAggregate.create_draft(
        name="Lady Teresa",
        entity_type=EntityType.CHARACTER,
        summary="A mortal ranger captain",
        description="She fought the undying wraiths and defended the mortal villagers at great personal sacrifice.",
    )
    jev = OpenJevLoreAdapter()
    auditor = AuditEntityUseCase(
        memory_port=InMemoryLoreMemoryAdapter(),
        event_publisher=InMemoryEventPublisherAdapter(),
        jev_port=jev,
    )
    res = auditor.execute(entity)
    assert res.is_valid is True, f"False positive detected: {res.contradictions}"


def test_false_positive_explicit_negation(world_bible):
    """Explicitly stating someone is NOT immortal must pass."""
    entity = LoreEntityAggregate.create_draft(
        name="Scholar Vaelen",
        entity_type=EntityType.CHARACTER,
        summary="A mortal historian",
        description="He was not immortal and never claimed divinity, knowing well that all men must turn to dust.",
    )
    jev = OpenJevLoreAdapter()
    auditor = AuditEntityUseCase(
        memory_port=InMemoryLoreMemoryAdapter(),
        event_publisher=InMemoryEventPublisherAdapter(),
        jev_port=jev,
    )
    res = auditor.execute(entity)
    assert res.is_valid is True, f"False positive detected: {res.contradictions}"


def test_false_positive_beneficiary_cost(world_bible):
    """'without cost to the innocent' while paying personal cost must not be flagged."""
    entity = LoreEntityAggregate.create_draft(
        name="High Priest Orin",
        entity_type=EntityType.CHARACTER,
        summary="A devoted cleric",
        description="He purified the water wells without cost to the poor villagers, sacrificing ten years of his own lifespan.",
    )
    jev = OpenJevLoreAdapter()
    auditor = AuditEntityUseCase(
        memory_port=InMemoryLoreMemoryAdapter(),
        event_publisher=InMemoryEventPublisherAdapter(),
        jev_port=jev,
    )
    res = auditor.execute(entity)
    assert res.is_valid is True, f"False positive detected: {res.contradictions}"


def test_false_positive_relative_death_fact(world_bible):
    """A fact stating Kaelen's father died must not cause a temporal paradox for Kaelen."""
    kaelen = LoreEntityAggregate.create_draft(
        name="Kaelen",
        entity_type=EntityType.CHARACTER,
        summary="A knight commander",
        description="Kaelen served honorably in the army.",
        timeline_point=TimelinePoint(era="First Age", year=150),
    )
    fact = LoreFact(
        fact_id="f1",
        entity_name="Kaelen's father",
        statement="Kaelen's father died in year 100 after a long illness.",
    )
    report = DomainConsistencyPolicy.audit_entity(
        entity=kaelen,
        world_bible=world_bible,
        canonical_facts=[fact],
    )
    assert report.is_valid is True, f"False positive temporal paradox: {report.contradictions}"


def test_false_positive_entity_resolution_short_names():
    """Distinct short names like Alden and Aldon must not be falsely merged."""
    resolver = EntityResolutionService(match_threshold=0.85)
    name1, m1 = resolver.resolve("Alden")
    name2, m2 = resolver.resolve("Aldon")

    assert name1 == "Alden" and m1 is False
    assert name2 == "Aldon" and m2 is False, f"Aldon was falsely merged into {name2}"


def test_true_positive_actual_violations_still_caught(world_bible):
    """True violations must still be strictly caught and rejected."""
    violating = LoreEntityAggregate.create_draft(
        name="Malakor the Undying",
        entity_type=EntityType.CHARACTER,
        summary="An immortal tyrant",
        description="Became immortal and cast infinite magic without sacrifice.",
    )
    jev = OpenJevLoreAdapter()
    auditor = AuditEntityUseCase(
        memory_port=InMemoryLoreMemoryAdapter(),
        event_publisher=InMemoryEventPublisherAdapter(),
        jev_port=jev,
    )
    res = auditor.execute(violating)
    assert res.is_valid is False
    assert len(res.contradictions) > 0
