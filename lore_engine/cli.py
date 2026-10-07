import argparse
import sys
import os
import yaml
from typing import List

from .models import WorldBible, Task, EntityType
from .store import LoreStore
from .judge import LoreJudge
from .llm import LoreLLMClient
from .engine import AutonomousLoreEngine


def load_yaml_config(config_path: str):
    """Loads world and initial seed tasks from YAML file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    raw_world = data.get("world", {})
    world = WorldBible(
        name=raw_world.get("name", "Северное Порубежье: Явь и Навь"),
        cosmology=raw_world.get("cosmology", ""),
        immutable_laws=raw_world.get("immutable_laws", []),
        tone=raw_world.get("tone", "dark_slavic_fantasy"),
    )

    settings = data.get("settings", {})
    tasks_data = data.get("tasks", [])
    seed_tasks = []

    for t in tasks_data:
        t_type = t.get("type", "generate")
        if t_type == "generate":
            raw_e_type = t.get("entity_type")
            e_type = None
            if raw_e_type:
                for member in EntityType:
                    if member.value == raw_e_type.lower():
                        e_type = member
                        break
            seed_tasks.append(Task(
                name=t.get("name", "Неизвестный"),
                entity_type=e_type,
                hint=t.get("prompt", ""),
                depth=0,
                priority=10,
            ))
        elif t_type == "swarm":
            # Extract high-level prompt as seed task
            seed_tasks.append(Task(
                name="Древний Клан Волхвов",
                entity_type=EntityType.FACTION,
                hint="Древний тайный орден чародеев и волхвов Нави, черпающих морозную силу",
                depth=0,
                priority=9,
            ))

    return world, settings, seed_tasks


def main():
    parser = argparse.ArgumentParser(description="Autonomous Red-Links Lore Engine with Self-Healing Reflection")
    parser.add_argument("--config", "-c", default="configs/tasks_ru.yml", help="Path to YAML configuration")
    parser.add_argument("--max-entities", "-m", type=int, default=6, help="Maximum entities budget to generate")
    parser.add_argument("--max-depth", "-d", type=int, default=3, help="Maximum graph link traversal depth")
    parser.add_argument("--db", default="output/lore_engine.db", help="SQLite database path")
    parser.add_argument("--mock", action="store_true", help="Force local deterministic mock LLM mode")
    parser.add_argument("--live", action="store_true", help="Force live OpenRouter LLM mode (overrides config)")
    parser.add_argument("--ollama", action="store_true", help="Use local Ollama instance on http://localhost:11434/v1")
    parser.add_argument("--model", default=None, help="LLM model override")

    args = parser.parse_args()

    world, settings, seed_tasks = load_yaml_config(args.config)
    output_results = settings.get("output_file", "output/lore_results_ru.json")
    output_memory = settings.get("memory_file", "output/lore_memory_ru.json")

    if args.live:
        use_mock = False
    elif args.mock:
        use_mock = True
    else:
        use_mock = bool(settings.get("use_mock_llm", False))

    base_url = "http://localhost:11434/v1" if args.ollama else None

    print("=" * 74)
    print(" 🌟 AUTONOMOUS RED-LINKS LORE ENGINE (v2.0)")
    print(f" 📖 Вселенная: '{world.name}' ({len(world.immutable_laws)} аксиомы)")
    print(f" 🎯 Бюджет: {args.max_entities} сущностей | Макс. глубина ссылок: {args.max_depth}")
    print(f" 🤖 Провайдер: {'Mock Mode' if use_mock else ('Local Ollama' if args.ollama else 'OpenRouter (Live API)')}")
    print(f" 🗄️ База данных: {os.path.abspath(args.db)}")
    print("=" * 74)

    store = LoreStore(db_path=args.db)
    llm = LoreLLMClient(
        base_url=base_url,
        model=args.model,
        use_mock=use_mock,
    )
    judge = LoreJudge(llm_client=llm, store=store)

    # Callbacks for real-time streaming progress
    counter = [0]

    def on_generated(entity, task, new_red_links):
        counter[0] += 1
        print(f"\n[{counter[0]}/{args.max_entities}] 🏛️ {entity.name} ({entity.entity_type.value.upper()}) | {entity.year} год ({entity.era})")
        print(f"   Саммари: {entity.summary}")
        print(f"   Факты ({len(entity.facts)}):")
        for f in entity.facts:
            print(f"     • {f}")
        print(f"   Связи ({len(entity.relations)}):")
        for r in entity.relations:
            print(f"     -> [{r.type}] {r.target} ({r.context})")

        if new_red_links:
            print(f"   🔗 Обнаружены «красные ссылки» (добавлены в очередь, глубина {task.depth + 1}):")
            for rl in new_red_links:
                print(f"     ➕ '{rl.name}' (из связи с {entity.name})")

    def on_repair(entity, problems, attempt):
        print(f"   ⚠️ Замечания судьи канона (попытка {attempt}/3):")
        for p in problems:
            print(f"     - {p}")
        print("   🔧 Автоматический ремонт через рефлексию...")

    engine = AutonomousLoreEngine(
        store=store,
        llm=llm,
        judge=judge,
        world_bible=world,
        max_entities=args.max_entities,
        max_depth=args.max_depth,
        on_entity_generated=on_generated,
        on_repair_attempt=on_repair,
    )

    # Seed initial queue if empty
    seeded = engine.seed(seed_tasks)
    if seeded > 0:
        print(f"🌱 Засеяно стартовых задач: {seeded}")

    # Run the autonomous expansion loop
    engine.run()

    # Export multi-tier memory and workflow results
    res_path = store.export_results_json(output_results)
    mem_path = store.export_memory_json(output_memory)

    print("\n" + "=" * 74)
    print(f" ✨ ГЕНЕРАЦИЯ ЗАВЕРШЕНА: {store.total_entities_count()} сущностей в графе, {store.queue_size()} в очереди.")
    print(f" 📄 Результаты: {res_path}")
    print(f" 💾 Слепок L0–L3 памяти: {mem_path}")
    print(f" 🗄️ База SQLite сохранена: {store.db_path}")
    print("=" * 74)


if __name__ == "__main__":
    main()
