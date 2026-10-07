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
from lore_builder.application.use_cases.orchestrate_swarm_use_case import OrchestrateSwarmUseCase
from lore_builder.infrastructure.adapters.resource.job_objects_adapter import JobObjectsResourceAdapter
from lore_builder.infrastructure.adapters.memory.in_memory_adapter import InMemoryLoreMemoryAdapter
from lore_builder.infrastructure.adapters.memory.tencent_memory_adapter import TencentAgentMemoryAdapter
from lore_builder.infrastructure.adapters.llm.mock_llm_adapter import MockLLMAdapter
from lore_builder.infrastructure.adapters.llm.openai_compatible_adapter import OpenAICompatibleLLMAdapter
from lore_builder.infrastructure.adapters.event_publisher import InMemoryEventPublisherAdapter
from lore_builder.infrastructure.adapters.audit.open_jev_lore_adapter import OpenJevLoreAdapter


from lore_builder.application.services.yaml_workflow_service import YamlWorkflowParser
from lore_builder.application.use_cases.execute_workflow_use_case import ExecuteWorkflowUseCase


def build_container(use_live_tencent: bool = False, use_mock_llm: bool = False):
    if use_live_tencent:
        memory = TencentAgentMemoryAdapter()
    else:
        memory = InMemoryLoreMemoryAdapter()

    # Strictly loads native C++ JobObjects_RD (fails if native dylib/dll missing)
    resources = JobObjectsResourceAdapter()
    events = InMemoryEventPublisherAdapter()
    jev = OpenJevLoreAdapter()

    if use_mock_llm:
        llm = MockLLMAdapter(should_violate_canon=False)
    else:
        # Strictly queries OpenRouter using credentials from .env
        llm = OpenAICompatibleLLMAdapter()

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
    workflow_executor = ExecuteWorkflowUseCase(
        memory_port=memory,
        generator=generator,
        orchestrator=orchestrator,
        auditor=auditor,
        jev_port=jev,
    )
    return memory, generator, orchestrator, jev, workflow_executor


def execute_yaml_file(file_path: str, use_live_tencent: bool = False, use_mock_llm: bool = False) -> None:
    """Parses and executes a YAML workflow specification file."""
    workflow = YamlWorkflowParser.load_from_file(file_path)

    effective_tencent = use_live_tencent or workflow.settings.use_tencent_memory
    effective_mock_llm = use_mock_llm or workflow.settings.use_mock_llm

    memory, generator, orchestrator, jev, executor = build_container(
        use_live_tencent=effective_tencent,
        use_mock_llm=effective_mock_llm,
    )

    print("=" * 72)
    print(" 🌟 LORE AI BUILDER — DECLARATIVE YAML WORKFLOW EXECUTION")
    print(f" Specification File: {os.path.abspath(file_path)} (v{workflow.version})")
    print(f" Total Tasks: {len(workflow.tasks)}")
    if workflow.world:
        print(f" Target World: '{workflow.world.name}' ({len(workflow.world.immutable_laws)} immutable laws)")
    print("=" * 72)

    result = executor.execute(workflow)

    for item in result.task_results:
        idx = item["task_index"]
        t_type = item["task_type"]
        status = item["status"]
        print(f"\n[TASK {idx}/{len(workflow.tasks)}] {t_type.upper()} [{status}]")
        if status == "SUCCESS":
            res = item["result"]
            if t_type == "generate":
                print(f"  • Entity: {res['entity_name']} ({res['entity_type']}) - Status: {res['status'].upper()}")
                print(f"    Summary: {res['summary']}")
                print(f"    Facts: {len(res['facts'])} committed to L1")
            elif t_type == "swarm":
                print(f"    Waves: {res['total_waves']} | Entities generated: {res['entities_count']} | Facts: {res['facts_committed']}")
                for e in res["entities"]:
                    print(f"      - {e['name']} ({e['type']})")
            elif t_type == "audit":
                print(f"    Verdict: {res['verdict']} | P(Compliant): {res['p_compliant']:.3f} | Risk: {res['distortion_risk_score']:.2f}/3.00")
                print(f"    {res['explanation']}")
            elif t_type == "classify":
                print(f"    Relation: '{res['entity_a']}' --[{res['chosen_relation']}]--> '{res['entity_b']}' (Conf: {res['confidence']:.3f})")
            elif t_type == "temporal":
                print(f"    Allen Relation: '{res['interval_a']}' is [{res['allen_relation'].upper()}] relative to '{res['interval_b']}'")
            elif t_type == "score":
                print(f"    Distortion Risk Score: {res['score']:.2f}/3.00 (Conf: {res['confidence']:.3f})")
            elif t_type == "graph":
                print(f"    Wiki Node: {res.get('node', '')} | Outbound links: {res.get('outbound_links', [])}")
            elif t_type == "show-world":
                print(f"    World: '{res['name']}' | Cosmology: {res['cosmology']}")
        else:
            print(f"  ❌ Error: {item['error']}")

    print("\n" + "=" * 72)
    print(f" ✨ WORKFLOW FINISHED: {result.successful_tasks} succeeded, {result.failed_tasks} failed out of {result.total_tasks} tasks.")
    if result.output_file_written:
        print(f" 📄 Output exported to: {result.output_file_written}")
    print("=" * 72)


def main():
    # Check for direct YAML file passed as first argument: python3 -m lore_builder.presentation.cli tasks.yml
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and (sys.argv[1].endswith(".yml") or sys.argv[1].endswith(".yaml")):
        file_path = sys.argv[1]
        use_tencent = "--tencent" in sys.argv
        use_mock = "--mock-llm" in sys.argv
        execute_yaml_file(file_path, use_live_tencent=use_tencent, use_mock_llm=use_mock)
        return

    # Check for -c / --config flags
    for i, arg in enumerate(sys.argv):
        if arg in ("-c", "--config") and i + 1 < len(sys.argv):
            file_path = sys.argv[i + 1]
            use_tencent = "--tencent" in sys.argv
            use_mock = "--mock-llm" in sys.argv
            execute_yaml_file(file_path, use_live_tencent=use_tencent, use_mock_llm=use_mock)
            return

    parser = argparse.ArgumentParser(
        description="Lore AI Builder — Hexagonal DDD Engine (YAML Tasks & CLI)",
        usage="%(prog)s [tasks.yml | command] [options]",
    )
    parser.add_argument("-c", "--config", dest="config_flag", help="Path to YAML task specification file")
    parser.add_argument("--tencent", action="store_true", help="Connect to live TencentDB memory endpoint")
    parser.add_argument("--mock-llm", action="store_true", help="Use offline Mock LLM instead of OpenRouter")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run (YAML workflow)
    run_parser = subparsers.add_parser("run", help="Execute tasks defined in a YAML specification file")
    run_parser.add_argument("file", help="Path to .yml / .yaml file")

    # Command: show-world
    subparsers.add_parser("show-world", help="Display the active World Bible (L3)")

    # Command: generate
    gen_parser = subparsers.add_parser("generate", help="Generate a single lore entity")
    gen_parser.add_argument("--name", required=True, help="Entity name")
    gen_parser.add_argument("--type", default="character", choices=[e.value for e in EntityType], help="Entity type")
    gen_parser.add_argument("--prompt", required=True, help="Details / background hint")
    gen_parser.add_argument("--era", default="First Age", help="Historical Era")
    gen_parser.add_argument("--year", type=int, default=100, help="Timeline Year")

    # Command: swarm (Full DAG Multi-Agent Pipeline)
    swarm_parser = subparsers.add_parser("swarm", help="Run multi-agent swarm DAG pipeline from a high-level worldbuilding prompt")
    swarm_parser.add_argument("--prompt", required=True, help="High-level world prompt (e.g. 'Create the necromancer clan, their paladin enemies, and their war')")

    # Command: graph
    graph_parser = subparsers.add_parser("graph", help="Query entity Wiki link graph")
    graph_parser.add_argument("--name", required=True, help="Entity name")

    # Command: jev-audit
    jev_audit_parser = subparsers.add_parser("jev-audit", help="Run Jev System-1 calibrated canon audit on narrative")
    jev_audit_parser.add_argument("--name", required=True, help="Entity name")
    jev_audit_parser.add_argument("--narrative", required=True, help="Entity narrative / deed description")

    # Command: jev-classify
    jev_cls_parser = subparsers.add_parser("jev-classify", help="Run Jev System-1 ontological relation classification")
    jev_cls_parser.add_argument("--source", required=True, help="Subject entity")
    jev_cls_parser.add_argument("--target", required=True, help="Object entity")
    jev_cls_parser.add_argument("--context", required=True, help="Narrative context describing their interaction")

    # Command: jev-score
    jev_score_parser = subparsers.add_parser("jev-score", help="Run Jev System-1 lore distortion risk scoring")
    jev_score_parser.add_argument("--narrative", required=True, help="Entity narrative")

    # Command: jev-temporal
    jev_temp_parser = subparsers.add_parser("jev-temporal", help="Run Jev System-1 Allen interval temporal relation classification")
    jev_temp_parser.add_argument("--a", required=True, help="First epoch/event")
    jev_temp_parser.add_argument("--b", required=True, help="Second epoch/event")
    jev_temp_parser.add_argument("--context", required=True, help="Historical timeline narrative context")

    args = parser.parse_args()

    # Check if a YAML task specification was provided directly
    yaml_target = None
    if args.config_file and (args.config_file.endswith(".yml") or args.config_file.endswith(".yaml") or os.path.exists(args.config_file)):
        yaml_target = args.config_file
    elif args.config_flag:
        yaml_target = args.config_flag
    elif args.command == "run" and hasattr(args, "file") and args.file:
        yaml_target = args.file

    if yaml_target:
        execute_yaml_file(
            file_path=yaml_target,
            use_live_tencent=args.tencent,
            use_mock_llm=args.mock_llm,
        )
        return

    memory, generator, orchestrator, jev, executor = build_container(
        use_live_tencent=args.tencent,
        use_mock_llm=args.mock_llm,
    )

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
        print(f"Status: {res.status.upper()}")
        print(f"Summary: {res.summary}")
        print(f"Timeline: {res.timeline}")
        print("\nFacts:")
        for f in res.facts:
            print(f"  • {f}")
        print("\nRelations:")
        for r in res.relations:
            print(f"  • {r['target']} [{r['type']}] ({r.get('context', '')})")

    elif args.command == "swarm":
        print(f"\n[SWARM ORCHESTRATION INITIATED]")
        result = orchestrator.execute(args.prompt)
        print(f"\n✨ SWARM GENERATION COMPLETE across {result.total_waves} topological wave(s)!")
        print(f"Entities committed: {len(result.entities_generated)}")
        print(f"Facts recorded in L1: {result.facts_committed}")
        for ent in result.entities_generated:
            print(f"\n• {ent.name} [{ent.entity_type}] - {ent.status.upper()}")
            print(f"  Summary: {ent.summary}")
            print(f"  Relations: {[r['target'] for r in ent.relations]}")

    elif args.command == "graph":
        g = memory.get_entity_wiki_graph(args.name)
        print(json.dumps(g, indent=2, ensure_ascii=False))

    elif args.command == "jev-audit":
        world = memory.get_world_bible()
        report = jev.audit_entity_canon(
            world_rules=world.render_prompt_context(),
            entity_name=args.name,
            entity_narrative=args.narrative,
            immutable_laws=world.immutable_laws,
        )
        print(f"\n⚡ [JEV SYSTEM-1 CANON AUDIT REPORT]")
        print(f"Entity: {args.name}")
        print(f"Recommended Verdict: {report.recommended_verdict}")
        print(f"Compliance P(Yes): {report.is_canon_consistent.p_yes:.3f} (Conf: {report.is_canon_consistent.confidence:.3f})")
        print(f"Distortion Risk Score: {report.lore_distortion_risk.score:.2f} / 3.00")
        print(f"Distortion Levels: {json.dumps(report.lore_distortion_risk.level_probabilities, indent=2)}")
        print(f"Axiom Evaluations:")
        for ax, dec in report.axiom_evaluations.items():
            print(f"  - [{dec.verdict}] '{ax}': P(comply)={dec.p_yes:.3f}, conf={dec.confidence:.3f}")
        print(f"Explanation: {report.explanation}")

    elif args.command == "jev-classify":
        candidates = ["allied_with", "enemy_of", "vassal_of", "ruler_of", "creator_of", "located_in", "worships", "opposes"]
        choice = jev.classify_relation_type(
            entity_a=args.source,
            entity_b=args.target,
            narrative_context=args.context,
            candidate_relations=candidates,
        )
        print(f"\n⚡ [JEV SYSTEM-1 ONTOLOGY CLASSIFICATION]")
        print(f"Relation: '{choice.entity_a}' --[{choice.relation}]--> '{choice.entity_b}'")
        print(f"Confidence: {choice.confidence:.3f}")
        print(f"Probability Distribution:")
        for opt, prob in sorted(choice.probabilities.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {opt}: {prob:.3f}")

    elif args.command == "jev-score":
        score_dec = jev.evaluate_lore_distortion_risk(
            world_context="High fantasy canon",
            entity_narrative=args.narrative,
        )
        print(f"\n⚡ [JEV SYSTEM-1 DISTORTION SCORE]")
        print(f"Expected Score: {score_dec.score:.2f} / 3.00 (Conf: {score_dec.confidence:.3f})")
        for lvl, prob in score_dec.level_probabilities.items():
            print(f"  • Level '{lvl}': {prob:.3f}")

    elif args.command == "jev-temporal":
        temp_dec = jev.classify_temporal_relation(
            interval_a=args.a,
            interval_b=args.b,
            narrative_context=args.context,
        )
        print(f"\n⚡ [JEV SYSTEM-1 TEMPORAL RELATION (ALLEN'S ALGEBRA)]")
        print(f"Allen Relation: '{temp_dec.interval_a}' is [{temp_dec.allen_relation.upper()}] relative to '{temp_dec.interval_b}'")
        print(f"Confidence: {temp_dec.confidence:.3f}")
        for rel, prob in sorted(temp_dec.probabilities.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {rel}: {prob:.3f}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
