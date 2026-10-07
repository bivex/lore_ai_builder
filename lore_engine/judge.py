import logging
from typing import List, Optional, Any
from .models import Entity, WorldBible, EntityType, Verdict

logger = logging.getLogger(__name__)


class LoreJudge:
    """Hybrid Lore Auditor combining deterministic structural & graph checks (Python/SQL)
    with semantic LLM-Judge (structured JSON Verdict), completely eliminating brittle regular expressions.
    """

    def __init__(self, llm_client: Optional[Any] = None, store: Optional[Any] = None):
        self.llm_client = llm_client
        self.store = store

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

        # 3. Facts completeness check
        if len(entity.facts) == 0:
            problems.append("Сущность должна содержать хотя бы 1-2 конкретных атомарных факта с указанием эпохи или года.")

        # 4. Graph Temporal & Relational Sanity (via SQLite if store provided)
        if self.store is not None:
            problems.extend(self._audit_graph_constraints(entity))

        # -------------------------------------------------------------
        # LAYER 2: Semantic Axiom Audit via LLM-Judge (Zero Regex)
        # -------------------------------------------------------------
        client = self.llm_client
        if client is None:
            from .llm import LoreLLMClient
            client = LoreLLMClient(use_mock=True)

        verdict: Verdict = client.audit_entity(entity, world_bible)
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
            for rel in entity.relations:
                target_row = conn.execute(
                    "SELECT year, era, entity_type FROM entities WHERE py_lower(TRIM(name)) = ?",
                    (rel.target.strip().casefold(),)
                ).fetchone()
                if target_row and target_row["year"] is not None:
                    # Mortal character vs historical event lifespan sanity check
                    if entity.entity_type == EntityType.CHARACTER and target_row["entity_type"] == "historical_event":
                        diff = abs(entity.year - target_row["year"])
                        if diff > 150:
                            problems.append(
                                f"Временной парадокс в графе: смертный персонаж {entity.name} ({entity.year} г.) "
                                f"связан с событием {rel.target} ({target_row['year']} г.), разница {diff} лет."
                            )
        return problems
