import pytest

from lore_builder.domain.services.temporal_validator import (
    TemporalConsistencyValidator,
    TimeInterval,
    AllenRelation,
)
from lore_builder.domain.services.entity_resolver import (
    EntityResolutionService,
    jaro_winkler_similarity,
    normalize_entity_name,
)
from lore_builder.domain.services.dag_decomposer import LoreDAGPlanner, LoreTaskNode
from lore_builder.domain.services.triplet_extractor import TripletExtractionService
from lore_builder.domain.model.value_objects import EntityType, RelationType
from lore_builder.application.services.context_optimizer import (
    ContextOptimizerService,
    ContextItem,
)
from lore_builder.application.use_cases.orchestrate_swarm_use_case import OrchestrateSwarmUseCase
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
from lore_builder.infrastructure.adapters.llm.mock_llm_adapter import MockLLMAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter


def test_allen_interval_algebra():
    t1 = TimeInterval(start_year=100, end_year=200)
    t2 = TimeInterval(start_year=250, end_year=300)
    assert t1.relation_to(t2) == AllenRelation.BEFORE

    t3 = TimeInterval(start_year=150, end_year=180)
    assert t3.relation_to(t1) == AllenRelation.DURING

    # Participation paradox
    valid, err = TemporalConsistencyValidator.validate_participation(
        participant_name="Lord Vane",
        participant_lifespan=TimeInterval(start_year=50, end_year=120),
        event_name="Battle of High Pass",
        event_time=TimeInterval(start_year=150),
    )
    assert not valid
    assert "died/ended in year 120" in err

    # Artifact anachronism
    valid_art, err_art = TemporalConsistencyValidator.validate_artifact_usage(
        artifact_name="Sun Blade",
        creation_time=TimeInterval(start_year=300),
        user_name="Knight Gerald",
        usage_time=TimeInterval(start_year=200),
    )
    assert not valid_art
    assert "forged in year 300" in err_art


def test_entity_resolution_deduplication():
    resolver = EntityResolutionService(match_threshold=0.85)
    resolver.register_canonical("The Ashen Clan", aliases=["Order of Ash"])

    # Normalization check
    assert normalize_entity_name("The Order of Sun") == "sun"
    assert normalize_entity_name("King Alden") == "alden"

    # Fuzzy match
    match_name, is_match = resolver.resolve("Ashen Clan")
    assert is_match
    assert match_name == "The Ashen Clan"

    # New entity
    new_name, is_new = resolver.resolve("The Void Seekers")
    assert not is_new
    assert new_name == "The Void Seekers"


def test_dag_topological_sort_and_cycle_detection():
    n1 = LoreTaskNode("t1", "Era 1", EntityType.ERA, "First era")
    n2 = LoreTaskNode("t2", "Faction A", EntityType.FACTION, "Faction", dependencies=["t1"])
    n3 = LoreTaskNode("t3", "Faction B", EntityType.FACTION, "Faction", dependencies=["t1"])
    n4 = LoreTaskNode("t4", "Great War", EntityType.HISTORICAL_EVENT, "War", dependencies=["t2", "t3"])

    waves = LoreDAGPlanner.topological_sort([n1, n2, n3, n4])
    assert len(waves) == 3
    assert [n.task_id for n in waves[0]] == ["t1"]
    assert set(n.task_id for n in waves[1]) == {"t2", "t3"}
    assert [n.task_id for n in waves[2]] == ["t4"]

    # Test cycle detection
    c1 = LoreTaskNode("c1", "A", EntityType.FACTION, "", dependencies=["c2"])
    c2 = LoreTaskNode("c2", "B", EntityType.FACTION, "", dependencies=["c1"])
    with pytest.raises(ValueError) as exc:
        LoreDAGPlanner.topological_sort([c1, c2])
    assert "Cycle detected" in str(exc.value)


def test_context_optimizer_rrf_and_knapsack():
    # Test RRF fusion
    bm25 = {"doc1": 1, "doc2": 2}
    vector = {"doc2": 1, "doc1": 2}
    graph = {"doc1": 1, "doc3": 2}
    scores = ContextOptimizerService.rrf_fuse(bm25, vector, graph, k=60)
    assert scores["doc1"] > scores["doc3"]

    # Test Knapsack packing with token budget
    items = [
        ContextItem(item_id="i1", content="Short highly relevant fact", relevance_score=1.0, token_cost=10, source_type="L1"),
        ContextItem(item_id="i2", content="Huge low relevance paragraph", relevance_score=0.2, token_cost=200, source_type="L0"),
        ContextItem(item_id="i3", content="Medium relevant fact", relevance_score=0.8, token_cost=20, source_type="L1"),
    ]
    packed = ContextOptimizerService.knapsack_pack(items, max_token_budget=50)
    assert any(i.item_id == "i1" for i in packed)
    assert any(i.item_id == "i3" for i in packed)
    assert not any(i.item_id == "i2" for i in packed)  # Should reject heavy, low-value item


def test_triplet_extraction():
    text = "The Ashen Clan commands the Iron Fortress in year 240. The Radiant Knights fought against the Ashen Clan."
    relations = TripletExtractionService.extract_triplets_and_relations("The Ashen Clan", text)
    assert len(relations) >= 1
    rel_targets = [r.target_entity_name for r in relations]
    assert any("Iron Fortress" in t for t in rel_targets) or any("Radiant Knights" in t for t in rel_targets)


def test_swarm_orchestration_end_to_end():
    memory = InMemoryLoreMemoryAdapter()
    resources = JobObjectsResourceAdapter()
    events = InMemoryEventPublisherAdapter()
    llm = MockLLMAdapter(should_violate_canon=False)

    orchestrator = OrchestrateSwarmUseCase(
        memory_port=memory,
        resource_controller=resources,
        llm_provider=llm,
        event_publisher=events,
    )

    prompt = (
        "Create the northern necromancer clan, their ancient feud with the sun paladins, "
        "their forbidden blood artifacts, and how the war changed their lands."
    )

    result = orchestrator.execute(prompt)
    assert result.total_waves >= 2
    assert len(result.entities_generated) >= 3
    assert result.facts_committed >= 3
    assert len(result.wiki_nodes) >= 3
