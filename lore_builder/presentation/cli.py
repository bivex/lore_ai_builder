import argparse
import sys
import os
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lore_builder.domain.model.value_objects import EntityType
from lore_builder.application.dto.entity_dto import GenerateEntityCommand
from lore_builder.application.use_cases.audit_entity_use_case import AuditEntityUseCase
from lore_builder.application.use_cases.generate_entity_use_case import GenerateEntityUseCase
from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.memory.tencent_memory_adapter import TencentAgentMemoryAdapter
from lore_builder.infrastructure.adapters.llm.mock_llm_adapter import MockLLMAdapter
from lore_builder.infrastructure.adapters.llm.openai_compatible_adapter import OpenAICompatibleLLMAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter


def build_container(use_live_tencent: bool = False, live_llm_url: str = None):
    if use_live_tencent:
        memory = TencentAgentMemoryAdapter()
    else:
        memory = InMemoryLoreMemoryAdapter()

    resources = JobObjectsResourceAdapter()
    events = InMemoryEventPublisherAdapter()

    if live_llm_url:
        llm = OpenAICompatibleLLMAdapter(base_url=live_llm_url)
    else:
        llm = MockLLMAdapter(should_violate_canon=False)

    auditor = AuditEntityUseCase(memory_port=memory, event_publisher=events)
    generator = GenerateEntityUseCase(
        memory_port=memory,
        resource_controller=resources,
        llm_provider=llm,
        event_publisher=events,
        audit_use_case=auditor,
    )
    return memory, generator


def main():
    parser = argparse.ArgumentParser(description="Lore AI Builder — Hexagonal DDD Engine")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: show-world
    subparsers.add_parser("show-world", help="Display the active World Bible (L3)")

    # Command: generate
    gen_parser = subparsers.add_parser("generate", help="Generate a new lore entity")
    gen_parser.add_argument("--name", required=True, help="Entity name")
    gen_parser.add_argument("--type", default="character", choices=[e.value for e in EntityType], help="Entity type")
    gen_parser.add_argument("--prompt", required=True, help="Details / background hint")
    gen_parser.add_argument("--era", default="First Age", help="Historical Era")
    gen_parser.add_argument("--year", type=int, default=100, help="Timeline Year")

    # Command: query-graph
    graph_parser = subparsers.add_parser("graph", help="Query entity Wiki link graph")
    graph_parser.add_argument("--name", required=True, help="Entity name")

    args = parser.parse_args()
    memory, generator = build_container()

    if args.command == "show-world":
        bible = memory.get_world_bible()
        print(bible.render_prompt_context())

    elif args.command == "generate":
        entity_type = EntityType(args.type)
        cmd = GenerateEntityCommand(
            name=args.name,
            entity_type=entity_type,
            prompt_hint=args.prompt,
            era=args.era,
            year=args.year,
        )
        res = generator.execute(cmd)
        print(f"\n[CANON COMMITTED]: {res.name} ({res.entity_type})")
        print(f"Summary: {res.summary}")
        print(f"Timeline: {res.timeline}")
        print("Facts:")
        for f in res.facts:
            print(f"  • {f}")
        print("Relations:")
        for r in res.relations:
            print(f"  • {r['target']} [{r['type']}]")

    elif args.command == "graph":
        g = memory.get_entity_wiki_graph(args.name)
        print(json.dumps(g, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
