import re
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from ..model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from ..model.entity import LoreFact
from .temporal_validator import TemporalConsistencyValidator, TimeInterval


@dataclass(frozen=True)
class ConsistencyReport:
    is_valid: bool
    contradictions: List[str] = field(default_factory=list)
    confidence_score: float = 1.0
    notes: str = ""


class DomainConsistencyPolicy:
    """Domain Service that audits proposed lore changes against World Bible axioms, known facts, and Allen's temporal algebra."""

    @staticmethod
    def audit_entity(
        entity: LoreEntityAggregate,
        world_bible: WorldBibleAggregate,
        canonical_facts: List[LoreFact],
    ) -> ConsistencyReport:
        contradictions: List[str] = []

        # 1. Check against World Bible Immutable Laws (L3)
        entity_text = f"{entity.summary} {entity.description}".lower()
        for law in world_bible.immutable_laws:
            law_lower = law.lower()
            if "no magic" in law_lower and "cast powerful magic" in entity_text:
                contradictions.append(f"Violates world law: '{law}'")
            if "mortal" in law_lower and ("immortal" in entity_text or "undying" in entity_text):
                contradictions.append(f"Violates mortality rule in law: '{law}'")

        # 2. Check against Known Canonical Facts (L1) & Temporal Contradictions
        year_regex = re.compile(r"\b(?:in\s+year|year)\s+(\d+)\b", re.IGNORECASE)
        died_regex = re.compile(r"\bdied(?:\s+in\s+year|\s+in)?\s+(\d+)\b", re.IGNORECASE)

        for fact in canonical_facts:
            fact_lower = fact.statement.lower()

            # Check death vs active timeline point
            if entity.name.lower() in fact_lower and "died" in fact_lower:
                death_match = died_regex.search(fact_lower)
                if death_match and entity.timeline_point:
                    death_year = int(death_match.group(1))
                    if entity.timeline_point.year > death_year:
                        valid, err = TemporalConsistencyValidator.validate_participation(
                            participant_name=entity.name,
                            participant_lifespan=TimeInterval(start_year=0, end_year=death_year),
                            event_name=f"Activity at {entity.timeline_point}",
                            event_time=TimeInterval(start_year=entity.timeline_point.year),
                        )
                        if not valid:
                            contradictions.append(err)

            # Direct contradiction check
            if f"not {entity.name.lower()}" in fact_lower:
                contradictions.append(f"Contradicts known canon fact: '{fact.statement}'")

        # 3. Check for circular or self-conflicting relations
        for rel in entity.relations:
            if rel.target_entity_name.lower() == entity.name.lower():
                contradictions.append(f"Entity cannot have self-relation: {rel.relation_type}")

        is_valid = len(contradictions) == 0
        notes = "Canon consistency check passed" if is_valid else f"Detected {len(contradictions)} conflict(s)"
        return ConsistencyReport(
            is_valid=is_valid,
            contradictions=contradictions,
            confidence_score=1.0 if is_valid else 0.0,
            notes=notes,
        )
