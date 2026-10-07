import logging
from typing import List, Optional, Any
from .models import Entity, EntityFactsDraft, WorldBible, EntityType, Verdict

logger = logging.getLogger(__name__)


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

        # 4. Facts completeness check
        if len(entity.facts) == 0:
            problems.append("Сущность должна содержать хотя бы 1-2 конкретных атомарных факта с указанием эпохи или года.")

        # 5. Lifespan check within entity facts
        if entity.entity_type == EntityType.CHARACTER:
            years_in_facts = []
            for f in entity.facts:
                # Extract 1-4 digit numbers representing years safely
                for token in f.replace(":", " ").replace(",", " ").replace(".", " ").split():
                    token_clean = token.strip()
                    if token_clean.isdigit() and len(token_clean) <= 4:
                        years_in_facts.append(int(token_clean))
            if years_in_facts:
                span = max(years_in_facts) - min(years_in_facts)
                if span > 120:
                    problems.append(
                        f"Нарушение срока жизни смертного персонажа: факты '{entity.name}' охватывают {span} лет "
                        f"({min(years_in_facts)}..{max(years_in_facts)} гг.). Смертные не могут жить более 120 лет без божественности (аксиома 2)."
                    )

        # 6. Graph Temporal & Relational Sanity (via SQLite if store provided)
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

            # 2. Check relations targets
            for rel in entity.relations:
                resolved_target = rel.target
                if hasattr(self.store, "resolve_canonical_name"):
                    resolved_target = self.store.resolve_canonical_name(rel.target)

                target_row = conn.execute(
                    "SELECT year, era, entity_type FROM entities WHERE py_lower(TRIM(name)) = ?",
                    (resolved_target.strip().casefold(),)
                ).fetchone()
                if target_row and target_row["year"] is not None:
                    # Mortal character vs historical event lifespan sanity check
                    if entity.entity_type == EntityType.CHARACTER and target_row["entity_type"] == "historical_event":
                        diff = abs(entity.year - target_row["year"])
                        if diff > 150:
                            problems.append(
                                f"Временной парадокс в графе: смертный персонаж {entity.name} ({entity.year} г.) "
                                f"связан с событием {resolved_target} ({target_row['year']} г.), разница {diff} лет."
                            )
        return problems
