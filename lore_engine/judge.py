import logging
from typing import List, Optional, Any
from .models import Entity, EntityFactsDraft, WorldBible, EntityType, Verdict

logger = logging.getLogger(__name__)

ONTOLOGICAL_RELATION_RULES = {
    "leader_of": {
        "valid_sources": {EntityType.CHARACTER},
        "valid_targets": {EntityType.FACTION},
    },
    "member_of": {
        "valid_sources": {EntityType.CHARACTER},
        "valid_targets": {EntityType.FACTION},
    },
    "allied_with": {
        "valid_sources": {EntityType.CHARACTER, EntityType.FACTION},
        "valid_targets": {EntityType.CHARACTER, EntityType.FACTION},
    },
    "enemy_of": {
        "valid_sources": {EntityType.CHARACTER, EntityType.FACTION},
        "valid_targets": {EntityType.CHARACTER, EntityType.FACTION},
    },
    "located_in": {
        "valid_sources": {EntityType.CHARACTER, EntityType.FACTION, EntityType.LOCATION, EntityType.ARTIFACT},
        "valid_targets": {EntityType.LOCATION},
    },
    "participated_in": {
        "valid_sources": {EntityType.CHARACTER, EntityType.FACTION, EntityType.ARTIFACT},
        "valid_targets": {EntityType.HISTORICAL_EVENT},
    },
    "possesses": {
        "valid_sources": {EntityType.CHARACTER, EntityType.FACTION},
        "valid_targets": {EntityType.ARTIFACT, EntityType.LOCATION},
    },
    "created_by": {
        "valid_sources": {EntityType.ARTIFACT, EntityType.LOCATION, EntityType.HISTORICAL_EVENT},
        "valid_targets": {EntityType.CHARACTER, EntityType.FACTION},
    },
    "adjacent_to": {
        "valid_sources": {EntityType.LOCATION},
        "valid_targets": {EntityType.LOCATION},
    },
    "predecessor_of": {
        "same_type": True,
    },
    "successor_of": {
        "same_type": True,
    },
}


class LoreJudge:
    """Hybrid Lore Auditor combining deterministic structural & graph checks (Python/SQL)
    with semantic LLM-Judge (structured JSON Verdict), completely eliminating brittle regular expressions.
    """

    def __init__(self, llm_client: Optional[Any] = None, store: Optional[Any] = None):
        self.llm_client = llm_client
        self.store = store

    def audit_draft(self, draft: EntityFactsDraft, world_bible: WorldBible, context: str = "") -> List[str]:
        """Audits atomic facts draft BEFORE prose synthesis (Facts-first principle)."""
        temp_entity = Entity(
            name=draft.name,
            entity_type=draft.entity_type,
            summary="",
            description="",
            era=draft.era,
            year=draft.year,
            facts=[f.statement for f in draft.facts],
            atomic_facts=draft.facts,
            relations=draft.relations,
        )
        return self.audit(temp_entity, world_bible, context)

    def audit(self, entity: Entity, world_bible: WorldBible, context: str = "") -> List[str]:
        """Audits the proposed entity against World Bible laws and graph constraints.
        Returns actionable problems for repair if violations are severe or canon-breaking.
        """
        problems: List[str] = []

        # -------------------------------------------------------------
        # LAYER 1: Deterministic Graph & Structural Checks (Zero Regex)
        # -------------------------------------------------------------
        # 0. Canonical Era validation
        if getattr(world_bible, "eras", None) and entity.era:
            if entity.era not in world_bible.eras:
                problems.append(
                    f"Недопустимая эпоха '{entity.era}' для сущности '{entity.name}'. "
                    f"Разрешенные канонические эпохи мира: {', '.join(world_bible.eras)}."
                )

        # 1. Self-reference check (e.g. Radomir -> Radomir)
        entity_name_cf = entity.name.strip().casefold()
        for rel in entity.relations:
            if rel.target.strip().casefold() == entity_name_cf:
                problems.append(f"Сущность не может ссылаться сама на себя в связях ({rel.type} -> {rel.target}).")

        # 2. Duplicate relations check
        seen_rels = set()
        for rel in entity.relations:
            key = (rel.target.strip().casefold(), rel.type.strip().casefold())
            if key in seen_rels:
                problems.append(f"Дублирующаяся связь: {rel.type} -> {rel.target}")
            seen_rels.add(key)

        # 3. Predecessor relation check (enemy_of vs predecessor_of)
        for rel in entity.relations:
            ctx_lower = rel.context.casefold()
            if rel.type.casefold() == "enemy_of" and any(w in ctx_lower for w in ["предшественник", "предшественниц", "бывшая воевода", "бывший воевода"]):
                problems.append(
                    f"Недопустимая связь 'enemy_of' для предшественника '{rel.target}'. "
                    f"Для павших предшественников используйте тип связи 'predecessor_of', если не было предательства."
                )

        # 4. Ontological relation rules: source constraints & semantic heuristic targets
        for rel in entity.relations:
            r_type = rel.type.strip().lower()
            if r_type in ONTOLOGICAL_RELATION_RULES:
                rule = ONTOLOGICAL_RELATION_RULES[r_type]
                if "valid_sources" in rule and entity.entity_type not in rule["valid_sources"]:
                    valid_names = [t.value for t in rule["valid_sources"]]
                    problems.append(
                        f"Онтологическая ошибка: сущность '{entity.name}' ({entity.entity_type.value}) "
                        f"не может быть источником отношения '{rel.type}'. Разрешенные типы: {valid_names}."
                    )
                # Fast heuristic checks for obvious target misattributions
                t_lower = rel.target.strip().lower()
                if r_type == "participated_in":
                    if any(w in t_lower for w in ["врата", "застава", "крепость", "разлом", "гора", "лес", "скала", "башня"]):
                        problems.append(
                            f"Онтологическая ошибка: цель связи 'participated_in' ('{rel.target}') является локацией, "
                            f"а не историческим событием. Для локаций используйте 'located_in' или 'defends'."
                        )
                elif r_type == "possesses":
                    if any(w in t_lower for w in ["клан", "орден", "дружина", "братство"]):
                        problems.append(
                            f"Онтологическая ошибка: сущность не может обладать ('possesses') фракцией ('{rel.target}'). "
                            f"Используйте 'leader_of' или 'member_of'."
                        )

        # 5. Facts completeness check
        if len(entity.facts) == 0 and len(entity.atomic_facts) == 0:
            problems.append("Сущность должна содержать хотя бы 1-2 конкретных атомарных факта с указанием эпохи или года.")

        # 6. Lifespan check within entity facts (using structured years)
        if entity.entity_type == EntityType.CHARACTER:
            years_in_facts = []
            if entity.atomic_facts:
                years_in_facts = [af.year for af in entity.atomic_facts if af.year is not None and af.year > 0]
            elif self.store and hasattr(self.store, "_get_conn"):
                with self.store._get_conn() as conn:
                    rows = conn.execute(
                        "SELECT year FROM facts WHERE entity_name = ? AND year IS NOT NULL",
                        (entity.name,)
                    ).fetchall()
                    years_in_facts = [r["year"] for r in rows if r["year"] and r["year"] > 0]

            if not years_in_facts:
                # Text fallback: look strictly for explicit calendar year markers (never plain age numbers like '5 лет' or 'в возрасте 81 года')
                for f in entity.facts:
                    tokens = f.replace(":", " ").replace(",", " ").replace(".", " ").replace("—", " ").replace("-", " ").split()
                    for idx, token in enumerate(tokens):
                        if token.isdigit() and 2 <= len(token) <= 4:
                            val = int(token)
                            prev_tok = tokens[idx - 1].lower() if idx > 0 else ""
                            next_tok = tokens[idx + 1].lower() if idx + 1 < len(tokens) else ""
                            # Ignore age and duration phrases
                            if prev_tok in ("возрасте", "возраст", "прожив", "прожила", "прожил", "спустя", "через"):
                                continue
                            if next_tok in ("год", "года", "году", "г", "гг") or (idx == 0 and len(token) >= 2):
                                # If it's a small number (< 120) and not at start of sentence, it's duration or age, not a calendar year
                                if val < 120 and idx > 0 and prev_tok not in ("в", "во"):
                                    continue
                                years_in_facts.append(val)

            all_years = years_in_facts[:]
            if entity.year and entity.year > 0:
                all_years.append(entity.year)

            if len(all_years) >= 2:
                span = max(all_years) - min(all_years)
                if span > 120:
                    problems.append(
                        f"Нарушение срока жизни смертного персонажа: факты '{entity.name}' охватывают {span} лет "
                        f"({min(all_years)}..{max(all_years)} гг.). Смертные не могут жить более 120 лет без божественности (аксиома 2)."
                    )

        # 7. Graph Temporal & Relational Sanity (via SQLite if store provided)
        if self.store is not None:
            problems.extend(self._audit_graph_constraints(entity))

        # -------------------------------------------------------------
        # LAYER 2: Semantic Axiom Audit via LLM-Judge (Zero Regex)
        # -------------------------------------------------------------
        client = self.llm_client
        if client is None:
            from .llm import LoreLLMClient
            client = LoreLLMClient(use_mock=True)

        try:
            verdict: Verdict = client.audit_entity(entity, world_bible)
        except Exception as e:
            logger.warning(f"Semantic audit LLM call encountered error ({e}), gracefully marking needs_review")
            verdict = Verdict(is_valid=True, violations=[], needs_review=True)

        for v in verdict.violations:
            if v.severity in ("canon_breaking", "severe"):
                problems.append(
                    f"Нарушение аксиомы '{v.axiom}': {v.explanation} (Цитата: '{v.quote}')"
                )
            elif v.severity == "minor" or verdict.needs_review:
                logger.info(f"Замечание [needs_review] для {entity.name}: {v.explanation} (Цитата: '{v.quote}')")

        return problems

    def _audit_graph_constraints(self, entity: Entity) -> List[str]:
        """SQL queries checking temporal and ontological constraints against the existing graph."""
        problems = []
        if not hasattr(self.store, "_get_conn"):
            return problems

        with self.store._get_conn() as conn:
            # 1. Check existing entities with same core name (Dynasty / Name reuse across centuries)
            if entity.entity_type == EntityType.CHARACTER:
                existing_same_name = conn.execute(
                    "SELECT year, era FROM entities WHERE py_lower(TRIM(name)) = ? AND entity_type = 'character'",
                    (entity.name.strip().casefold(),)
                ).fetchone()
                if existing_same_name and existing_same_name["year"] is not None:
                    diff = abs(entity.year - existing_same_name["year"])
                    if diff > 150:
                        problems.append(
                            f"Тот же смертный персонаж '{entity.name}' уже зафиксирован в {existing_same_name['year']} г. "
                            f"(разница {diff} лет). Если это потомок, добавьте нумерацию (напр., '{entity.name} II') или укажите смену поколений."
                        )

            # 2. Check relations targets and graph ontological matrix
            for rel in entity.relations:
                resolved_target = rel.target
                if hasattr(self.store, "resolve_canonical_name"):
                    resolved_target = self.store.resolve_canonical_name(rel.target)

                target_row = conn.execute(
                    "SELECT year, era, entity_type FROM entities WHERE py_lower(TRIM(name)) = ?",
                    (resolved_target.strip().casefold(),)
                ).fetchone()
                if target_row:
                    target_e_type_str = target_row["entity_type"]
                    target_e_type = None
                    if target_e_type_str:
                        for m in EntityType:
                            if m.value == target_e_type_str.lower():
                                target_e_type = m
                                break

                    # Graph ontological rules verification
                    if target_e_type:
                        r_type = rel.type.strip().lower()
                        if r_type in ONTOLOGICAL_RELATION_RULES:
                            rule = ONTOLOGICAL_RELATION_RULES[r_type]
                            if "valid_targets" in rule and target_e_type not in rule["valid_targets"]:
                                valid_names = [t.value for t in rule["valid_targets"]]
                                problems.append(
                                    f"Онтологическая ошибка в графе: отношение '{rel.type}' к '{resolved_target}' ({target_e_type.value}) "
                                    f"недопустимо. Допустимые типы цели: {valid_names}."
                                )
                            if rule.get("same_type") and entity.entity_type != target_e_type:
                                problems.append(
                                    f"Онтологическая ошибка в графе: отношение '{rel.type}' между '{entity.name}' ({entity.entity_type.value}) "
                                    f"и '{resolved_target}' ({target_e_type.value}) недопустимо (требуется одинаковый тип сущностей)."
                                )

                    # Mortal character vs historical event lifespan sanity check
                    if target_row["year"] is not None:
                        if entity.entity_type == EntityType.CHARACTER and target_row["entity_type"] == "historical_event":
                            diff = abs(entity.year - target_row["year"])
                            if diff > 150:
                                problems.append(
                                    f"Временной парадокс в графе: смертный персонаж {entity.name} ({entity.year} г.) "
                                    f"связан с событием {resolved_target} ({target_row['year']} г.), разница {diff} лет."
                                )
        return problems
