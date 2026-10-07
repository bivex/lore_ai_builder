import os
import json
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


def test_hybrid_judge_deterministic_graph_checks_and_verdict():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)
        world = WorldBible(
            name="Явь и Навь",
            immutable_laws=["Смертные не могут обрести истинное бессмертие или стать богами"],
        )
        llm = LoreLLMClient(use_mock=True)
        judge = LoreJudge(llm_client=llm, store=store)

        # 1. Commit historical event in year 500
        event = Entity(
            name="Великая Стужа",
            entity_type=EntityType.HISTORICAL_EVENT,
            summary="Катастрофическая зима",
            description="Ледяная буря Нави",
            year=500,
            facts=["500 год — замерзание рек."],
            relations=[],
        )
        store.commit_entity(event)

        # 2. Character in year 100 pointing to year 500 event (temporal paradox) and self-reference
        violating_char = Entity(
            name="Охотник Яромир",
            entity_type=EntityType.CHARACTER,
            summary="Обычный охотник, не ставший бессмертным",
            description="Охотник Яромир никогда не был бессмертным и не искал божественности.",
            year=100,
            facts=["100 год — родился в тайге."],
            relations=[
                Relation(target="Охотник Яромир", type="allied_with", context="Сам себе союзник"),
                Relation(target="Великая Стужа", type="participated_in", context="Жил спустя 400 лет"),
            ],
        )

        problems = judge.audit(violating_char, world)
        # Should catch self-reference and temporal paradox without ANY regexes
        assert any("ссылаться сама на себя" in p for p in problems)
        assert any("Временной парадокс в графе" in p for p in problems)
        # But NOT mortality violation because of negation "не был бессмертным"
        assert not any("аксиомы" in p for p in problems)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_two_stage_facts_first_pipeline_and_alias_resolution():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)
        world = WorldBible(
            name="Явь и Навь",
            immutable_laws=["Смертные не могут обрести истинное бессмертие или стать богами"],
        )
        llm = LoreLLMClient(use_mock=True)
        judge = LoreJudge(llm_client=llm, store=store)

        # 1. Test alias deduplication
        char1 = Entity(
            name="Рунный кузнец Вараг",
            entity_type=EntityType.CHARACTER,
            summary="Мастер рун",
            description="Опытный кузнец",
            year=325,
            facts=["325 год: Выковал молот."],
            relations=[],
        )
        store.commit_entity(char1)

        # Alias 'Вараг' should resolve to 'Рунный кузнец Вараг'
        assert store.resolve_canonical_name("Вараг") == "Рунный кузнец Вараг"
        assert store.exists_entity("Вараг") is True

        # 2. Test lifespan audit check (85 to 310 year span = 225 years)
        old_char = Entity(
            name="Архиволхв Мороз",
            entity_type=EntityType.CHARACTER,
            summary="Древний волхв",
            description="Основатель",
            year=85,
            facts=[
                "85 год: Основал клан волхвов.",
                "310 год: Просил перековать молот.",
            ],
            relations=[],
        )
        problems_lifespan = judge.audit(old_char, world)
        assert any("срока жизни" in p for p in problems_lifespan)

        # 3. Test predecessor relation check (enemy_of for predecessor)
        predecessor_ent = Entity(
            name="Воевода Радомир",
            entity_type=EntityType.CHARACTER,
            summary="Воевода",
            description="Защитник",
            year=338,
            facts=["338 год: Принял командование."],
            relations=[
                Relation(target="Воевода Ксения", type="enemy_of", context="Погибшая предшественница воеводы"),
            ],
        )
        problems_pred = judge.audit(predecessor_ent, world)
        assert any("predecessor_of" in p for p in problems_pred)

        # 4. Test L0 conversation recording and results export
        engine = AutonomousLoreEngine(
            store=store,
            llm=llm,
            judge=judge,
            max_entities=2,
            max_depth=1,
        )
        engine.seed([Task(name="Северная Дружина", entity_type=EntityType.FACTION)])
        engine.run()

        # Check conversation recording
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf_json:
            json_path = tf_json.name
        try:
            store.export_memory_json(json_path)
            with open(json_path, "r", encoding="utf-8") as f:
                mem_data = json.load(f)
            assert len(mem_data["l0_conversations"]) >= 1
            assert "session_" in mem_data["l0_conversations"][0]["session_id"]
        finally:
            if os.path.exists(json_path):
                os.remove(json_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_lifespan_false_positive_eliminated():
    """Verify that numbers representing age/costs (e.g. '78 лет', '5 лет души')
    are NOT treated as calendar years and do not falsely flag lifespan violations.
    """
    judge = LoreJudge()
    world = WorldBible()

    char = Entity(
        name="Ветеран Всеслав",
        entity_type=EntityType.CHARACTER,
        summary="Старый защитник Рубежа",
        description="Ветеран многих битв",
        era="Первая Эпоха",
        year=742,
        facts=[
            "742 год: в 78 лет на Рубеже защитил заставу, сжигая 5 лет души.",
            "745 год: пал смертью храбрых в возрасте 81 года.",
        ],
        relations=[],
    )
    problems = judge.audit(char, world)
    # Must NOT have lifespan violation!
    assert not any("срока жизни" in p for p in problems), f"Unexpected lifespan violation: {problems}"


def test_lifespan_with_structured_atomic_facts():
    judge = LoreJudge()
    world = WorldBible()
    from lore_engine.models import AtomicFact

    # 1. Valid span: 50 years (300 to 350)
    valid_draft_char = Entity(
        name="Воин Добрыня",
        entity_type=EntityType.CHARACTER,
        summary="Доблестный витязь",
        description="Защитник",
        era="Первая Эпоха",
        year=300,
        facts=["Родился в 300 году", "Пал в 350 году"],
        atomic_facts=[
            AtomicFact(year=300, statement="300 год: Родился."),
            AtomicFact(year=350, statement="350 год: Пал в битве."),
        ],
        relations=[],
    )
    problems = judge.audit(valid_draft_char, world)
    assert not any("срока жизни" in p for p in problems)

    # 2. Invalid span: 200 years (100 to 300)
    invalid_draft_char = Entity(
        name="Старец Ратмир",
        entity_type=EntityType.CHARACTER,
        summary="Смертный воин",
        description="Воин",
        era="Первая Эпоха",
        year=100,
        facts=["Родился в 100 году", "Жив в 300 году"],
        atomic_facts=[
            AtomicFact(year=100, statement="100 год: Родился."),
            AtomicFact(year=300, statement="300 год: Жив."),
        ],
        relations=[],
    )
    problems_inv = judge.audit(invalid_draft_char, world)
    assert any("срока жизни" in p for p in problems_inv)


def test_ontological_relation_matrix_enforcement():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)
        judge = LoreJudge(store=store)
        world = WorldBible()

        # Seed location and faction
        loc = Entity(
            name="Врата Нави",
            entity_type=EntityType.LOCATION,
            summary="Прорыв Нави",
            description="Ледяной разлом",
            year=100,
            facts=["100 год: Разлом образовался."],
            relations=[],
        )
        faction = Entity(
            name="Северная Дружина",
            entity_type=EntityType.FACTION,
            summary="Рать защитников",
            description="Воины",
            year=100,
            facts=["100 год: Дружина сформирована."],
            relations=[],
        )
        store.commit_entity(loc)
        store.commit_entity(faction)

        # 1. Location possessing a faction -> Invalid source/target
        invalid_loc = Entity(
            name="Каменная Глыба",
            entity_type=EntityType.LOCATION,
            summary="Скала",
            description="Утёс",
            year=100,
            facts=["100 год: Стоит скала."],
            relations=[
                Relation(target="Северная Дружина", type="possesses", context="Скала владеет дружиной"),
            ],
        )
        problems1 = judge.audit(invalid_loc, world)
        assert any("Онтологическая ошибка" in p for p in problems1)

        # 2. Faction participated_in Location -> Invalid target (participated_in requires historical_event)
        invalid_rel_event = Entity(
            name="Лесной Клан",
            entity_type=EntityType.FACTION,
            summary="Охотники",
            description="Клан",
            year=100,
            facts=["100 год: Основан клан."],
            relations=[
                Relation(target="Врата Нави", type="participated_in", context="Клан участвовал во Вратах"),
            ],
        )
        problems2 = judge.audit(invalid_rel_event, world)
        assert any("Онтологическая ошибка" in p for p in problems2)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_canonical_eras_validation():
    judge = LoreJudge()
    world = WorldBible(eras=["Первая Эпоха", "Вторая Эпоха"])

    bad_era_entity = Entity(
        name="Механический Страж",
        entity_type=EntityType.ARTIFACT,
        summary="Голем",
        description="Страж",
        era="Эпоха Паровых Машин",  # Invalid era!
        year=100,
        facts=["100 год: Создан страж."],
        relations=[],
    )
    problems = judge.audit(bad_era_entity, world)
    assert any("Недопустимая эпоха" in p for p in problems)


def test_alias_resolution_strict_vs_grammatical_inflection():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)

        # Register "Воевода Ксения" and "Радомир"
        store.commit_entity(Entity(
            name="Воевода Ксения",
            entity_type=EntityType.CHARACTER,
            summary="Воевода",
            description="Воительница",
            year=100,
            facts=["100 год: Возглавила дружину."],
            relations=[],
        ))
        store.commit_entity(Entity(
            name="Радомир",
            entity_type=EntityType.CHARACTER,
            summary="Воин",
            description="Витязь",
            year=100,
            facts=["100 год: Защитил слободу."],
            relations=[],
        ))

        # 1. Russian grammatical case declensions MUST match
        assert store.resolve_canonical_name("Ксении") == "Воевода Ксения"
        assert store.resolve_canonical_name("Ксению") == "Воевода Ксения"
        assert store.resolve_canonical_name("Радомира") == "Радомир"
        assert store.resolve_canonical_name("Радомиром") == "Радомир"

        # 2. Distinct short names like "Радик" vs "Радим" must NEVER be falsely merged
        store.commit_entity(Entity(
            name="Радим",
            entity_type=EntityType.CHARACTER,
            summary="Охотник",
            description="Следопыт",
            year=100,
            facts=["100 год: Пришел с севера."],
            relations=[],
        ))
        assert store.resolve_canonical_name("Радик") == "Радик"  # Must NOT resolve to Радим!
        assert store.exists_entity("Радик") is False
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_task_lifecycle_retry_and_recovery():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)
        task = Task(name="Крепость Заслон", depth=0, priority=5)
        store.push_task(task)

        # 1. Pop task marks it in_progress
        popped = store.pop_task()
        assert popped is not None
        assert popped.status == "in_progress"
        assert store.queue_size() == 0

        # 2. Recovery on startup resets dangling in_progress tasks
        reset_cnt = store.reset_in_progress_tasks()
        assert reset_cnt == 1
        assert store.queue_size() == 1

        # 3. Fail task retry counting
        popped = store.pop_task()
        assert popped.retry_count == 0

        # Attempt 1 fail -> back to pending with retry_count = 1
        store.fail_task(popped.name, error="Timeout 1", max_retries=3)
        assert store.queue_size() == 1

        popped2 = store.pop_task()
        assert popped2.retry_count == 1

        # Attempt 2 fail -> back to pending with retry_count = 2
        store.fail_task(popped2.name, error="Timeout 2", max_retries=3)
        assert store.queue_size() == 1

        popped3 = store.pop_task()
        assert popped3.retry_count == 2

        # Attempt 3 fail -> transitions to 'failed'
        store.fail_task(popped3.name, error="Timeout 3", max_retries=3)
        assert store.queue_size() == 0  # No longer pending

        with store._get_conn() as conn:
            row = conn.execute("SELECT status, retry_count, error_message FROM queue WHERE name = 'Крепость Заслон'").fetchone()
            assert row["status"] == "failed"
            assert row["retry_count"] == 3
            assert row["error_message"] == "Timeout 3"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_facts_table_structured_fields_and_audit_export():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = LoreStore(db_path=db_path)
        from lore_engine.models import AtomicFact

        # Commit entity with structured facts and audit notes
        ent = Entity(
            name="Кузнец Ивар",
            entity_type=EntityType.CHARACTER,
            summary="Мастер молота",
            description="Кует рунные доспехи",
            era="Первая Эпоха",
            year=210,
            facts=["210 год: Выковал щит."],
            atomic_facts=[
                AtomicFact(year=210, era="Первая Эпоха", statement="210 год: Выковал щит.", participants=["Ивар"]),
            ],
            audit_status="needs_review",
            audit_issues=["Замечание по хронологии."],
            relations=[],
        )
        store.commit_entity(ent)

        with store._get_conn() as conn:
            fact_row = conn.execute("SELECT year, era, participants FROM facts WHERE entity_name = 'Кузнец Ивар'").fetchone()
            assert fact_row["year"] == 210
            assert fact_row["era"] == "Первая Эпоха"
            assert "Ивар" in fact_row["participants"]

            ent_row = conn.execute("SELECT audit_status, audit_issues FROM entities WHERE name = 'Кузнец Ивар'").fetchone()
            assert ent_row["audit_status"] == "needs_review"
            assert "хронологии" in ent_row["audit_issues"]

        # Test results export
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f_res:
            res_path = f_res.name
        try:
            store.export_results_json(res_path)
            with open(res_path, "r", encoding="utf-8") as f:
                res_data = json.load(f)
            assert len(res_data) == 1
            assert res_data[0]["status"] == "NEEDS_REVIEW"
            assert res_data[0]["audit"]["status"] == "needs_review"
            assert len(res_data[0]["audit"]["issues"]) == 1
        finally:
            if os.path.exists(res_path):
                os.remove(res_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
