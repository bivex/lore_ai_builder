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
    def _is_true_mortality_violation(text: str) -> bool:
        """Distinguishes genuine claims of immortality/divinity from metaphorical usage, negations, or battling immortal foes."""
        # 1. Strip benign metaphorical phrases
        cleaned = re.sub(
            r"\b(?:undying|immortal)\s+(?:loyalty|devotion|love|friendship|gratitude|respect|oath|vow|memory|legacy|renown|glory|verse|poetry|words|fame|deeds|art|philosophy)\b",
            " ",
            text,
        )
        # 2. Strip antagonist phrases (hero fighting/slaying immortal foes)
        cleaned = re.sub(
            r"\b(?:fought|slayed|hunted|battled|opposed|defended\s+against|banished|survived)\s+(?:the\s+|an?\s+)?(?:immortal|undying)\b",
            " ",
            cleaned,
        )
        # 3. Strip explicit negations
        cleaned = re.sub(
            r"\b(?:not|never|refused|denied|without\s+being)\s+(?:an?\s+)?(?:immortal|undying|divinity)\b",
            " ",
            cleaned,
        )
        # 4. Genuine violations
        actual_violations = [
            r"\b(?:became|is|was|declared|ascended\s+as|achieved)\s+(?:an?\s+)?(?:immortal|undying|divine\s+god)\b",
            r"\b(?:achieved|gained|attained|stole)\s+(?:true\s+)?immortality\b",
            r"\b(?:cannot\s+die|never\s+dies|immune\s+to\s+death|defied\s+death\s+forever)\b",
            r"\bimmortal\s+(?:sorcerer|tyrant|king|emperor|warlord|ruler|being|mage)\b",
            r"\bundying\s+(?:sorcerer|tyrant|king|emperor|warlord|ruler|defier|abomination)\b",
        ]
        return any(re.search(pat, cleaned) for pat in actual_violations)

    @staticmethod
    def _is_true_sacrifice_violation(text: str) -> bool:
        """Distinguishes magic without cost from beneficiary descriptions (e.g. 'without cost to the villagers') and actual sacrifices."""
        # If narrative has explicit personal sacrifice, and doesn't claim infinite cost-free spells, it's valid
        has_explicit_sacrifice = bool(re.search(
            r"\b(?:sacrificing|sacrificed|gave\s+up|paid\s+with|burnt|lost\s+his|lost\s+her|offered\s+his|offered\s+her)\b",
            text
        ))
        if has_explicit_sacrifice and not re.search(r"\b(?:infinite|unlimited)\s+(?:magic|mana|spells?)\s+without\s+sacrifice\b", text):
            return False

        # Strip beneficiary phrases like "without cost to the villagers/realm"
        cleaned = re.sub(
            r"\b(?:without|at\s+no)\s+(?:cost|sacrifice)\s+to\s+(?:the|his|her|their|people|villagers|citizens|realm|poor|others|mortal)\b",
            " ",
            text,
        )
        # Strip negations
        cleaned = re.sub(
            r"\b(?:not|never|no\s+\w+)\s+(?:without\s+cost|without\s+sacrifice)\b",
            " ",
            cleaned,
        )

        violation_patterns = [
            r"\b(?:cast|casting|channeled|wielded|performed)\s+(?:magic|spells?)\s+(?:without|with\s+no)\s+(?:cost|sacrifice|price)\b",
            r"\b(?:magic|spells?)\s+without\s+(?:cost|sacrifice)\b",
            r"\b(?:infinite|unlimited)\s+(?:magic|mana|spells?)\s+(?:without|with\s+no)\s+(?:cost|sacrifice)\b",
            r"\bcast\s+infinite\s+magic\b",
            r"\bwithout\s+cost\s+or\s+sacrifice\b",
            r"\bwithout\s+sacrifice\s+or\s+cost\b",
        ]
        return any(re.search(pat, cleaned) for pat in violation_patterns)

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
            if "no magic" in law_lower and re.search(r"\b(?:cast|used|channeled)\s+(?:powerful\s+)?magic\b", entity_text):
                contradictions.append(f"Violates world law: '{law}'")
            if "mortal" in law_lower or "cannot achieve true divinity" in law_lower:
                if DomainConsistencyPolicy._is_true_mortality_violation(entity_text):
                    contradictions.append(f"Violates mortality rule in law: '{law}'")
            if "sacrifice" in law_lower:
                if DomainConsistencyPolicy._is_true_sacrifice_violation(entity_text):
                    contradictions.append(f"Violates sacrifice rule in law: '{law}'")

        # 2. Check against Known Canonical Facts (L1) & Temporal Contradictions
        died_regex = re.compile(
            rf"\b{re.escape(entity.name.lower())}\s+(?:himself\s+|herself\s+)?died(?:\s+in\s+year|\s+in)?\s+(\d+)\b",
            re.IGNORECASE
        )
        death_of_regex = re.compile(
            rf"\bdeath\s+of\s+{re.escape(entity.name.lower())}(?:\s+in\s+year|\s+in)?\s+(\d+)\b",
            re.IGNORECASE
        )

        for fact in canonical_facts:
            fact_lower = fact.statement.lower()

            # Ensure the deceased subject is indeed THIS entity, and NOT a relative
            # (e.g. NOT "Kaelen's father died in year 100")
            is_relative = bool(re.search(rf"\b{re.escape(entity.name.lower())}['’]s\s+\w+\s+died\b", fact_lower))
            if not is_relative and (fact.entity_name.lower() == entity.name.lower() or entity.name.lower() in fact_lower):
                death_match = died_regex.search(fact_lower) or death_of_regex.search(fact_lower)
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

            # Direct contradiction check (entity explicitly denied existence)
            if re.search(rf"\b{re.escape(entity.name.lower())}\s+(?:never\s+existed|is\s+fictional|does\s+not\s+exist)\b", fact_lower):
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
