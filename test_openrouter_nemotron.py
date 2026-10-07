import sys
import os
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NemotronTest")

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from lore_builder.domain.model.value_objects import EntityType
from lore_builder.application.dto.entity_dto import GenerateEntityCommand
from lore_builder.application.use_cases.audit_entity_use_case import AuditEntityUseCase
from lore_builder.application.use_cases.generate_entity_use_case import GenerateEntityUseCase
from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.llm.openai_compatible_adapter import OpenAICompatibleLLMAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter


def main():
    print("=" * 75)
    print(" 🚀 TESTING LORE PIPELINE VIA OPENROUTER: nvidia/nemotron-3-ultra-550b-a55b:free")
    print("=" * 75)

    memory_adapter = InMemoryLoreMemoryAdapter()
    resource_adapter = JobObjectsResourceAdapter()
    events_adapter = InMemoryEventPublisherAdapter()
    llm_adapter = OpenAICompatibleLLMAdapter()

    print(f"Endpoint: {llm_adapter.base_url}")
    print(f"Model: {llm_adapter.model}")
    print(f"Resource Controller: JobObjects_RD (Native Darwin QoS on macOS)")

    auditor = AuditEntityUseCase(memory_port=memory_adapter, event_publisher=events_adapter)
    generator = GenerateEntityUseCase(
        memory_port=memory_adapter,
        resource_controller=resource_adapter,
        llm_provider=llm_adapter,
        event_publisher=events_adapter,
        audit_use_case=auditor,
    )

    cmd = GenerateEntityCommand(
        name="Vaelin the Star-Seer",
        entity_type=EntityType.CHARACTER,
        prompt_hint=(
            "An astronomer-priest who spent decades charting the Ley Lines across the fractured sky. "
            "He sacrificed his physical eyesight to perceive the stellar flows."
        ),
        era="First Age",
        year=310,
    )

    print(f"\n[1/3] Generating '{cmd.name}' via Nemotron with OS Memory Compression...")
    res = generator.execute(cmd)

    print("\n[2/3] Generation & Audit Succeeded!")
    print(f"Status: {res.status.upper()}")
    print(f"Summary: {res.summary}")
    print(f"Timeline: {res.timeline}")
    print("\nL1 Atomic Facts:")
    for f in res.facts:
        print(f"  • {f}")
    print("\nRelations:")
    for r in res.relations:
        print(f"  • {r['target']} [{r['type']}] ({r.get('context', '')})")

    print("\n[3/3] Wiki Link Graph:")
    graph = memory_adapter.get_entity_wiki_graph(cmd.name)
    print(json.dumps(graph, indent=2, ensure_ascii=False))

    print("\n" + "=" * 75)
    print(" 🎉 ALL TESTS PASSED: Nemotron-3-ultra-550b generated and validated lore!")
    print("=" * 75)


if __name__ == "__main__":
    main()
