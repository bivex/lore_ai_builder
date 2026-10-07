import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

from ..model.value_objects import RelationType, EntityRelation
from ..model.entity import LoreFact


@dataclass(frozen=True)
class ExtractedTriplet:
    subject: str
    predicate: str
    object: str
    time_qualifier: Optional[str] = None


class TripletExtractionService:
    """Algorithm extracting structured knowledge graph triplets and atomic facts from unstructured lore narrative (L0 -> L1)."""

    # Patterns for detecting common entity relations in narrative text
    RELATION_PATTERNS = [
        (re.compile(r"(\b[A-Z][\w\s]+?)\s+(?:was\s+founded\s+by|was\s+created\s+by|was\s+forged\s+by)\s+([A-Z][\w\s]+)", re.IGNORECASE), RelationType.CREATED_BY),
        (re.compile(r"(\b[A-Z][\w\s]+?)\s+(?:is\s+the\s+commander\s+of|rules|leads|commands)\s+([A-Z][\w\s]+)", re.IGNORECASE), RelationType.LEADER_OF),
        (re.compile(r"(\b[A-Z][\w\s]+?)\s+(?:allied\s+with|sworn\s+to|stands\s+with)\s+([A-Z][\w\s]+)", re.IGNORECASE), RelationType.ALLIED_WITH),
        (re.compile(r"(\b[A-Z][\w\s]+?)\s+(?:fought\s+against|opposes|enemy\s+of|wages\s+war\s+on)\s+([A-Z][\w\s]+)", re.IGNORECASE), RelationType.ENEMY_OF),
        (re.compile(r"(\b[A-Z][\w\s]+?)\s+(?:is\s+located\s+in|dwells\s+in|resides\s+in)\s+([A-Z][\w\s]+)", re.IGNORECASE), RelationType.LOCATED_IN),
        (re.compile(r"(\b[A-Z][\w\s]+?)\s+(?:wields|possesses|carries|holds)\s+([A-Z][\w\s]+)", re.IGNORECASE), RelationType.POSSESSES),
        (re.compile(r"(\b[A-Z][\w\s]+?)\s+(?:participated\s+in|fought\s+at|took\s+part\s+in)\s+([A-Z][\w\s]+)", re.IGNORECASE), RelationType.PARTICIPATED_IN),
    ]

    YEAR_PATTERN = re.compile(r"\b(?:in\s+year|year)\s+(\d+)\b", re.IGNORECASE)

    @classmethod
    def extract_triplets_and_relations(
        cls,
        entity_name: str,
        text: str,
    ) -> List[EntityRelation]:
        relations: List[EntityRelation] = []

        sentences = re.split(r"[.!?]\s+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            year_match = cls.YEAR_PATTERN.search(sentence)
            time_qualifier = f"Year {year_match.group(1)}" if year_match else None

            for pattern, rel_type in cls.RELATION_PATTERNS:
                match = pattern.search(sentence)
                if match:
                    subj, obj = match.group(1).strip(), match.group(2).strip()
                    # If subject is our entity, object is the target
                    if entity_name.lower() in subj.lower() and obj.lower() != entity_name.lower():
                        relations.append(
                            EntityRelation(
                                target_entity_name=obj,
                                relation_type=rel_type,
                                context=sentence,
                            )
                        )
                    # If object is our entity, subject is the target (inverting if necessary or keeping context)
                    elif entity_name.lower() in obj.lower() and subj.lower() != entity_name.lower():
                        relations.append(
                            EntityRelation(
                                target_entity_name=subj,
                                relation_type=rel_type,
                                context=sentence,
                            )
                        )

        return relations

    @classmethod
    def extract_atomic_facts(
        cls,
        entity_name: str,
        text: str,
        tags: Optional[List[str]] = None,
    ) -> List[str]:
        """Splits narrative into discrete assertion statements."""
        sentences = re.split(r"[.!?]\s+", text)
        facts: List[str] = []
        for s in sentences:
            cleaned = s.strip()
            if len(cleaned) >= 15 and (entity_name.lower() in cleaned.lower() or "he" in cleaned.lower() or "she" in cleaned.lower() or "they" in cleaned.lower()):
                facts.append(cleaned)
        return facts
