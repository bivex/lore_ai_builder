from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class JevNoulDecision:
    """Jev Noul Decision: Non-autoregressive Boolean verdict with calibrated probability."""
    instructions: str
    p_yes: float
    confidence: float
    axiom_tested: Optional[str] = None

    @property
    def p_no(self) -> float:
        return 1.0 - self.p_yes

    @property
    def verdict(self) -> bool:
        """Returns True if p_yes >= 0.5."""
        return self.p_yes >= 0.5

    def is_strongly_yes(self, threshold: float = 0.8) -> bool:
        return self.p_yes >= threshold

    def is_strongly_no(self, threshold: float = 0.2) -> bool:
        return self.p_yes <= threshold


@dataclass(frozen=True)
class JevChoiceDecision:
    """Jev Choice Decision: Categorical choice across predefined options with full probability distribution."""
    instructions: str
    chosen_option: str
    probabilities: Dict[str, float]
    confidence: float


@dataclass(frozen=True)
class JevScoreDecision:
    """Jev Score Decision: Ordinal assessment across calibrated levels (e.g. risk severity 0..3)."""
    instructions: str
    score: float
    levels: List[str]
    level_probabilities: Dict[str, float]
    confidence: float


@dataclass(frozen=True)
class LoreOntologyRelationChoice:
    """Lore-specific categorical relationship decision between two entities."""
    entity_a: str
    entity_b: str
    relation: str
    probabilities: Dict[str, float]
    confidence: float

    @property
    def chosen_option(self) -> str:
        return self.relation


@dataclass(frozen=True)
class LoreTemporalChoice:
    """Lore-specific temporal relationship decision (Allen's interval algebra)."""
    interval_a: str
    interval_b: str
    allen_relation: str
    probabilities: Dict[str, float]
    confidence: float

    @property
    def chosen_option(self) -> str:
        return self.allen_relation


@dataclass(frozen=True)
class JevCanonAuditReport:
    """Holistic System-1 canon audit report computed via parallel Jev typed decisions."""
    is_canon_consistent: JevNoulDecision
    lore_distortion_risk: JevScoreDecision
    axiom_evaluations: Dict[str, JevNoulDecision]
    recommended_verdict: str  # "APPROVE", "REJECT_AXIOM_VIOLATION", "FLAG_HIGH_RISK"
    explanation: str

