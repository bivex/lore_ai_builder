import os
import tempfile
import pytest

from lore_engine.models import Entity, Relation, Task, WorldBible, EntityType
from lore_engine.store import LoreStore
from lore_engine.judge import LoreJudge
from lore_engine.llm import LoreLLMClient
from lore_engine.engine import AutonomousLoreEngine


def test_models_validation():
    rel = Relation(target="Северная Дружина", type="leader_of", context="Командует ратью")
    ent = Entity(
        name="Радомир",
        entity_type=EntityType.CHARACTER,
        summary="Воевода рубежа",
        description="Храбрый воин",
        era="Первая Эпоха",
        year=115,
        facts=["Защитил заставу в 115 году."],
        relations=[rel],
    )
    assert ent.name == "Радомир"
    assert ent.entity_type == EntityType.CHARACTER
    assert len(ent.relations) == 1
    assert ent.relations[0].target == "Северная Дружина"


def test_lore_store_sqlite_crud_and_json_export():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)
        world = WorldBible(name="Явь и Навь", cosmology="Космология", immutable_laws=["Закон жертвы"])
        store.save_world(world)

        fetched_world = store.get_world()
        assert fetched_world.name == "Явь и Навь"
        assert len(fetched_world.immutable_laws) == 1

        # Push and pop tasks
        store.push_task(Task(name="Воевода Радомир", hint="Хранитель", depth=0, priority=10))
        store.push_task(Task(name="Древний Клан Волхвов", hint="Темные чародеи", depth=0, priority=5))
        assert store.queue_size() == 2

        task1 = store.pop_task()
        assert task1.name == "Воевода Радомир"
        assert store.queue_size() == 1

        # Commit entity
        rel = Relation(target="Северная Дружина", type="leader_of", context="Командует ратью")
        entity = Entity(
            name="Воевода Радомир",
            entity_type=EntityType.CHARACTER,
            summary="Воевода Заставы",
            description="Опытный воин, отдавший часть души за рубеж.",
            era="Первая Эпоха",
            year=115,
            facts=["Защитил Заставу в 115 году."],
            relations=[rel],
        )
        store.commit_entity(entity)
        assert store.exists_entity("Воевода Радомир") is True
        assert store.exists_entity("Несуществующий") is False

        # Export memory JSON
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out_f:
            json_path = out_f.name

        try:
            mem_path = store.export_memory_json(json_path)
            assert os.path.exists(mem_path)
            import json
            with open(mem_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert "l3_core" in data
                assert "l1_atomic_facts" in data
                assert "knowledge_wiki_graph" in data
                assert len(data["l1_atomic_facts"]) == 1
                assert "wiki_воевода_радомир" in data["knowledge_wiki_graph"]
        finally:
            if os.path.exists(json_path):
                os.remove(json_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_judge_canon_audit_and_false_positives():
    judge = LoreJudge()
    world = WorldBible(
        name="Явь и Навь",
        immutable_laws=[
            "Магия требует эквивалентной жертвы жизненной силы (закон сохранения чар)",
            "Смертные не могут обрести истинное бессмертие или стать богами",
        ],
    )

    # 1. Valid entity with metaphorical loyalty and true sacrifice
    valid_ent = Entity(
        name="Витязь Всеслав",
        entity_type=EntityType.CHARACTER,
        summary="Витязь Всеслав поклялся в бессмертной верности князю.",
        description="Пожертвовал глазом и частью жизненной силы при обороне рубежа, снискав бессмертную славу.",
        era="Первая Эпоха",
        year=115,
        facts=["Пожертвовал глазом ради защиты Яви в 115 году."],
        relations=[],
    )
    problems = judge.audit(valid_ent, world)
    assert len(problems) == 0, f"Expected 0 problems, got: {problems}"

    # 2. Invalid entity: true immortality and free magic
    invalid_ent = Entity(
        name="Кощей Пустотный",
        entity_type=EntityType.CHARACTER,
        summary="Бессмертный чародей Нави.",
        description="Творил бесконечную магию без жертвы и провозгласил себя вечным богом.",
        era="Первая Эпоха",
        year=115,
        facts=["Колдовал без платы."],
        relations=[],
    )
    problems_inv = judge.audit(invalid_ent, world)
    assert len(problems_inv) >= 2
    assert any("смертности" in p for p in problems_inv)
    assert any("жертвы" in p for p in problems_inv)


def test_autonomous_red_links_engine_mock_run():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)
        judge = LoreJudge()
        llm = LoreLLMClient(use_mock=True)

        engine = AutonomousLoreEngine(
            store=store,
            llm=llm,
            judge=judge,
            max_entities=4,
            max_depth=2,
        )

        seed = [
            Task(name="Воевода Радомир", entity_type=EntityType.CHARACTER, depth=0, priority=10),
        ]
        engine.seed(seed)

        # Run engine
        generated = engine.run()
        assert len(generated) == 4
        # First entity is seed: Воевода Радомир
        assert generated[0].name == "Воевода Радомир"

        # Subsequent entities must be the queued red links! (Северная Дружина, Застава Яви, etc.)
        names = [e.name for e in generated]
        assert "Северная Дружина" in names or "Застава Яви" in names

        # Check total committed in SQLite
        assert store.total_entities_count() == 4
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
