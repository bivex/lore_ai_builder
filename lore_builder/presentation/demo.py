import sys
import os
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LoreDemo")

# Add parent path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lore_builder.domain.model.value_objects import EntityType
from lore_builder.application.dto.entity_dto import GenerateEntityCommand
from lore_builder.application.use_cases.audit_entity_use_case import AuditEntityUseCase
from lore_builder.application.use_cases.generate_entity_use_case import GenerateEntityUseCase
from lore_builder.domain.exceptions import LoreCanonConflictError

from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.llm.mock_llm_adapter import MockLLMAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter
from lore_builder.infrastructure.adapters.audit.open_jev_lore_adapter import OpenJevLoreAdapter


def run_demonstration():
    print("=" * 70)
    print(" 🌟 LORE AI BUILDER — HEXAGONAL DDD DEMONSTRATION")
    print(" OS Kernel Shield + Hierarchical Memory + Jev System-1 Decision Engine")
    print("=" * 70)

    # 1. Composition Root / Dependency Injection
    print("\n[1/6] Bootstrapping Hexagonal Infrastructure...")
    memory_adapter = InMemoryLoreMemoryAdapter()
    resource_adapter = JobObjectsResourceAdapter()
    events_adapter = InMemoryEventPublisherAdapter()
    llm_adapter = MockLLMAdapter(should_violate_canon=False)
    jev_adapter = OpenJevLoreAdapter()

    # Subscribe to domain events
    events_adapter.subscribe(
        object, lambda ev: print(f"  [DOMAIN EVENT]: {type(ev).__name__} -> {getattr(ev, 'entity_name', '')}")
    )

    auditor_use_case = AuditEntityUseCase(
        memory_port=memory_adapter,
        event_publisher=events_adapter,
        jev_port=jev_adapter,
    )

    generator_use_case = GenerateEntityUseCase(
        memory_port=memory_adapter,
        resource_controller=resource_adapter,
        llm_provider=llm_adapter,
        event_publisher=events_adapter,
        audit_use_case=auditor_use_case,
    )

    # 2. Inspect World Bible (L3)
    world = memory_adapter.get_world_bible()
    print(f"\n[2/6] World Bible (L3 Core) Loaded: '{world.name}'")
    print(f"  Cosmology: {world.cosmology}")
    print("  Immutable Laws:")
    for law in world.immutable_laws:
        print(f"    • {law}")

    # 3. Generate Valid Canonical Entity (Character)
    print("\n[3/6] Generating Character 'Kaelen Voss' with OS Resource Control...")
    cmd_kaelen = GenerateEntityCommand(
        name="Kaelen Voss",
        entity_type=EntityType.CHARACTER,
        prompt_hint="Commander of the Silver Wardens, fought at Void Breach",
        era="First Age",
        year=245,
    )

    res_kaelen = generator_use_case.execute(cmd_kaelen)
    print(f"  ✅ Entity Generated & Verified: {res_kaelen.name} [{res_kaelen.status}]")
    print(f"  Summary: {res_kaelen.summary}")
    print(f"  Timeline: {res_kaelen.timeline}")
    print(f"  L1 Facts Committed: {len(res_kaelen.facts)}")
    for f in res_kaelen.facts:
        print(f"    - {f}")
    print(f"  Relations Established: {res_kaelen.relations}")

    # 4. Attempt to Generate Canon-Violating Entity (Conflict Audit Demo)
    print("\n[4/6] Testing Canon Defense: Attempting to introduce violating entity...")
    violating_llm = MockLLMAdapter(should_violate_canon=True)
    failing_generator = GenerateEntityUseCase(
        memory_port=memory_adapter,
        resource_controller=resource_adapter,
        llm_provider=violating_llm,
        event_publisher=events_adapter,
        audit_use_case=auditor_use_case,
    )

    cmd_malakor = GenerateEntityCommand(
        name="Malakor the Undying",
        entity_type=EntityType.CHARACTER,
        prompt_hint="An immortal sorcerer who casts infinite magic without sacrifice",
    )

    try:
        failing_generator.execute(cmd_malakor)
        print("  ❌ ERROR: Contradicting entity was unexpectedly admitted!")
    except LoreCanonConflictError as e:
        print(f"  🛡️ SUCCESS: Canon Defense successfully intercepted invalid entity!")
        print(f"     Reason: {e}")

    # 5. Jev System-1 Calibrated Typed Decisions for Lore
    print("\n[5/6] Jev System-1 Typed Decisions (sub-50ms non-autoregressive validation)...")
    jev_audit = jev_adapter.audit_entity_canon(
        world_rules=world.render_prompt_context(),
        entity_name="Malakor",
        entity_narrative="Immortal sorcerer casting infinite spells without sacrifice",
        immutable_laws=world.immutable_laws,
    )
    print(f"  • Canon Audit Verdict: {jev_audit.recommended_verdict}")
    print(f"  • P(Compliant): {jev_audit.is_canon_consistent.p_yes:.3f} | Distortion Risk: {jev_audit.lore_distortion_risk.score:.2f}/3.00")
    
    relation_choice = jev_adapter.classify_relation_type(
        entity_a="Commander Kaelen",
        entity_b="The Silver Wardens",
        narrative_context="Commander Kaelen leads and commands the Silver Wardens",
        candidate_relations=["allied_with", "ruler_of", "enemy_of", "vassal_of"],
    )
    print(f"  • Jev Ontology Choice: '{relation_choice.entity_a}' -> [{relation_choice.relation}] -> '{relation_choice.entity_b}' (conf: {relation_choice.confidence:.3f})")

    temporal_choice = jev_adapter.classify_temporal_relation(
        interval_a="The Primordial Dawn",
        interval_b="The Age of Iron",
        narrative_context="The Primordial Dawn occurred centuries prior to the Age of Iron",
    )
    print(f"  • Jev Allen Temporal Choice: '{temporal_choice.interval_a}' is [{temporal_choice.allen_relation.upper()}] relative to '{temporal_choice.interval_b}' (conf: {temporal_choice.confidence:.3f})")

    # 6. Inspect Wiki Link Graph
    print("\n[6/6] Querying Wiki Knowledge Graph for 'Kaelen Voss'...")
    graph = memory_adapter.get_entity_wiki_graph("Kaelen Voss")
    print(json.dumps(graph, indent=4))

    print("\n" + "=" * 70)
    print(" ✨ DEMONSTRATION COMPLETE: Full Hexagonal DDD pipeline with Jev operational!")
    print("=" * 70)


if __name__ == "__main__":
    run_demonstration()
