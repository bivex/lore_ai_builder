from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from ....domain.model.jev_decisions import (
    JevNoulDecision,
    JevChoiceDecision,
    JevScoreDecision,
    LoreOntologyRelationChoice,
    LoreTemporalChoice,
    JevCanonAuditReport,
)


class JevDecisionPort(ABC):
    """Outbound SPI port for non-autoregressive, calibrated System-1 typed decisions (Jev / Open-Jev)
    specifically tailored for worldbuilding and lore consistency.
    """

    @abstractmethod
    def evaluate_axiom_compliance(
        self,
        world_rules: str,
        entity_narrative: str,
        specific_rule: str,
    ) -> JevNoulDecision:
        """Returns Noul decision answering: 'Does this entity strictly comply with specific_rule?'."""
        pass

    @abstractmethod
    def batch_decide_lore_axioms(
        self,
        world_rules: str,
        entity_narrative: str,
        axioms: List[str],
    ) -> Dict[str, JevNoulDecision]:
        """Jev v3 'Read once, ask many' parallel pass evaluating all world axioms against an entity."""
        pass

    @abstractmethod
    def evaluate_lore_distortion_risk(
        self,
        world_context: str,
        entity_narrative: str,
    ) -> JevScoreDecision:
        """Returns Score decision rating distortion/contradiction severity across levels: ['none', 'minor', 'severe', 'canon_breaking']."""
        pass

    @abstractmethod
    def classify_relation_type(
        self,
        entity_a: str,
        entity_b: str,
        narrative_context: str,
        candidate_relations: List[str],
    ) -> LoreOntologyRelationChoice:
        """Returns Choice decision selecting the most accurate ontological relation type for the Wiki knowledge graph."""
        pass

    @abstractmethod
    def classify_temporal_relation(
        self,
        interval_a: str,
        interval_b: str,
        narrative_context: str,
        candidate_relations: Optional[List[str]] = None,
    ) -> LoreTemporalChoice:
        """Returns Choice decision selecting the Allen interval temporal relation between two historical epochs/events."""
        pass

    @abstractmethod
    def audit_entity_canon(
        self,
        world_rules: str,
        entity_name: str,
        entity_narrative: str,
        immutable_laws: List[str],
    ) -> JevCanonAuditReport:
        """Executes a single parallel decision pass over the entity against all world laws."""
        pass

