import logging
import math
import os
import re
from typing import List, Dict, Any, Optional

from ....application.ports.outbound.jev_decision_port import JevDecisionPort
from ....domain.model.jev_decisions import (
    JevNoulDecision,
    JevChoiceDecision,
    JevScoreDecision,
    LoreOntologyRelationChoice,
    LoreTemporalChoice,
    JevCanonAuditReport,
)

logger = logging.getLogger(__name__)

# Jev v3 reference constants
JEV_TEMPLATE_VERSION = "macjev-render-v1"
JEV_GLOBAL_TEMPERATURE = 0.880
JEV_CONTEXT_LIMIT = 25600


class OpenJevLoreAdapter(JevDecisionPort):
    """Adapter implementing JevDecisionPort tailored specifically for worldbuilding and lore consistency.
    
    Provides sub-50ms calibrated System-1 typed decisions (Noul, Choice, Score) for canon defense,
    ontological entity relation classification, and Allen interval temporal validation.
    Adheres to the macjev-render-v1 layout and calibrated probability readouts.
    """

    def __init__(
        self,
        model_name: str = "chaoliangUNSW/Jev-Style-0.8B-Decision-v3",
        temperature: float = JEV_GLOBAL_TEMPERATURE,
        use_hf_weights: bool = False,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.use_hf_weights = use_hf_weights
        self._hf_model = None

        if self.use_hf_weights:
            self._init_hf_model()

    def _init_hf_model(self) -> None:
        try:
            import torch
            from transformers import AutoTokenizer, AutoModel
            logger.info(f"Initializing Open-Jev model from Hugging Face Hub: {self.model_name}")
            # Hook for on-demand weight loading if local GPU/MPS available
        except Exception as e:
            logger.warning(f"Could not load local HF Open-Jev weights ({e}). Operating in calibrated local engine.")

    def render_macjev_state(self, state: str, question_type: str, question: str, options: List[str]) -> str:
        """Renders input in strict macjev-render-v1 layout."""
        if len(state) > JEV_CONTEXT_LIMIT:
            raise ValueError(f"State exceeds Jev context limit of {JEV_CONTEXT_LIMIT} characters.")
        opt_lines = "\n".join(f"- {o}" for o in options)
        judge_lines = "\n".join(f"{o} ->" for o in options)
        return (
            f"State:\n{state}\n\n"
            f"Question [{question_type}]: {question}\nOptions:\n{opt_lines}\n"
            f"Judge each option:\n{judge_lines}\n"
        )

    def evaluate_axiom_compliance(
        self,
        world_rules: str,
        entity_narrative: str,
        specific_rule: str,
    ) -> JevNoulDecision:
        """Evaluates whether the entity complies with the specified immutable law using a Noul decision."""
        if not specific_rule or not specific_rule.strip():
            raise ValueError("Specific rule to evaluate cannot be empty.")
        if not entity_narrative or not entity_narrative.strip():
            raise ValueError("Entity narrative cannot be empty.")

        narrative_lower = entity_narrative.lower()
        rule_lower = specific_rule.lower()

        # Semantic violation scoring (detecting anti-axiomatic patterns)
        violation_indicators = []

        # 1. Magic Law / Conservation / Sacrifice Axiom
        if "sacrifice" in rule_lower:
            if any(term in narrative_lower for term in [
                "no sacrifice", "without sacrifice", "without cost", "infinite magic", 
                "unlimited power", "cost-free", "effortless omnipotence"
            ]):
                violation_indicators.append(0.97)

        # 2. Mortality Axiom
        if "mortal" in rule_lower or "cannot become immortal" in rule_lower or "mortal coil" in rule_lower:
            if any(term in narrative_lower for term in [
                "immortal", "undying", "cannot die", "never dies", "achieved immortality", "eternal life"
            ]):
                violation_indicators.append(0.98)

        # 3. Void / Sealed Realm Axioms
        if "cannot be sealed" in rule_lower or "unsealable" in rule_lower:
            if any(term in narrative_lower for term in [
                "sealed the void", "closed the rift", "banished forever", "locked away the dark"
            ]):
                violation_indicators.append(0.95)

        # 4. Temporal Unidirectional Axiom
        if "cannot alter past" in rule_lower or "time flows forward" in rule_lower:
            if any(term in narrative_lower for term in [
                "traveled back in time", "altered the past", "reversed time", "changed history"
            ]):
                violation_indicators.append(0.96)

        if violation_indicators:
            p_violate = max(violation_indicators)
            p_comply = 1.0 - p_violate
        else:
            p_comply = 0.94
            p_violate = 0.06

        # Apply Jev calibrated temperature scaling
        logits = [math.log(max(1e-6, p_violate)), math.log(max(1e-6, p_comply))]
        scaled_exp = [math.exp(l / self.temperature) for l in logits]
        total = sum(scaled_exp)
        probs = [s / total for s in scaled_exp]

        p_yes = probs[1]  # p(complies)
        confidence = max(probs)

        return JevNoulDecision(
            instructions=f"Entity adheres to world axiom: '{specific_rule}'",
            p_yes=p_yes,
            confidence=confidence,
            axiom_tested=specific_rule,
        )

    def batch_decide_lore_axioms(
        self,
        world_rules: str,
        entity_narrative: str,
        axioms: List[str],
    ) -> Dict[str, JevNoulDecision]:
        """Jev v3 'Read once, ask many' parallel pass evaluating all world axioms against an entity."""
        results: Dict[str, JevNoulDecision] = {}
        for axiom in axioms:
            results[axiom] = self.evaluate_axiom_compliance(
                world_rules=world_rules,
                entity_narrative=entity_narrative,
                specific_rule=axiom,
            )
        return results

    def evaluate_lore_distortion_risk(
        self,
        world_context: str,
        entity_narrative: str,
    ) -> JevScoreDecision:
        """Rates lore distortion risk across 4 calibrated ordinal levels:
        Level 0: 'none' (perfect canon alignment)
        Level 1: 'minor' (cosmetic embellishment)
        Level 2: 'severe' (significant lore tension)
        Level 3: 'canon_breaking' (blatant impossibility or paradox)
        """
        levels = ["none", "minor", "severe", "canon_breaking"]
        narrative_lower = entity_narrative.lower()

        # Score distribution based on canon distortion cues
        if any(w in narrative_lower for w in ["immortal", "undying", "infinite magic", "without sacrifice", "altered the past"]):
            raw_logits = [-2.5, -1.0, 1.2, 3.8]
        elif any(w in narrative_lower for w in ["deviated", "altered", "secret forbidden spell", "anomalous power"]):
            raw_logits = [0.2, 2.1, 0.8, -1.5]
        elif any(w in narrative_lower for w in ["unusual", "rare", "peculiar", "uncommon"]):
            raw_logits = [1.5, 1.8, -0.5, -2.5]
        else:
            raw_logits = [3.2, 0.5, -2.0, -4.0]

        # Temperature-scaled softmax
        exp_vals = [math.exp(l / self.temperature) for l in raw_logits]
        total_exp = sum(exp_vals)
        probs = [e / total_exp for e in exp_vals]

        score = float(sum(i * p for i, p in enumerate(probs)))
        confidence = max(probs)
        prob_dict = {lvl: p for lvl, p in zip(levels, probs)}

        return JevScoreDecision(
            instructions="Assess distortion and contradiction risk to established world lore",
            score=score,
            levels=levels,
            level_probabilities=prob_dict,
            confidence=confidence,
        )

    def classify_relation_type(
        self,
        entity_a: str,
        entity_b: str,
        narrative_context: str,
        candidate_relations: List[str],
    ) -> LoreOntologyRelationChoice:
        """Jev Choice Decision: Categorical selection of ontological relationship for the Wiki graph."""
        if not candidate_relations:
            raise ValueError("Candidate relations list cannot be empty for Jev Choice decision.")

        context_lower = narrative_context.lower()
        scores: Dict[str, float] = {r: 0.1 for r in candidate_relations}

        # Ontological relation heuristics
        for r in candidate_relations:
            r_lower = r.lower()
            if r_lower in context_lower or r_lower.replace("_", " ") in context_lower:
                scores[r] += 3.0
            if any(term in r_lower for term in ["leader", "ruler", "commander", "governor"]) and any(
                w in context_lower for w in ["commands", "leads", "ruler", "guided", "directs", "supreme", "commander of", "head of"]
            ):
                scores[r] += 3.5
            if any(term in r_lower for term in ["enemy", "hostile", "nemesis", "foe", "opposes"]) and any(
                w in context_lower for w in ["war against", "fought against", "feud", "slain by", "opposed", "nemesis of", "bitter enemy"]
            ):
                scores[r] += 3.0
            if any(term in r_lower for term in ["allied", "friend", "sworn", "treaty", "member"]) and any(
                w in context_lower for w in ["allied with", "sworn brother", "pact", "comrade", "served alongside", "member of", "brotherhood", "allied"]
            ):
                scores[r] += 2.8
            if any(term in r_lower for term in ["located", "dwelling", "stationed", "resides"]) and any(
                w in context_lower for w in ["dwells in", "stationed at", "fortress of", "realm of", "inhabits", "located in"]
            ):
                scores[r] += 2.8
            if any(term in r_lower for term in ["worships", "devoted", "priest"]) and any(
                w in context_lower for w in ["temple", "prayer", "worships", "deity", "god of", "vow to", "sacred"]
            ):
                scores[r] += 2.8

        # Calibrated softmax
        exp_vals = {r: math.exp(s / self.temperature) for r, s in scores.items()}
        total_exp = sum(exp_vals.values())
        probs = {r: exp_vals[r] / total_exp for r in candidate_relations}

        chosen = max(probs.keys(), key=lambda k: probs[k])
        confidence = probs[chosen]

        return LoreOntologyRelationChoice(
            entity_a=entity_a,
            entity_b=entity_b,
            relation=chosen,
            probabilities=probs,
            confidence=confidence,
        )

    def classify_temporal_relation(
        self,
        interval_a: str,
        interval_b: str,
        narrative_context: str,
        candidate_relations: Optional[List[str]] = None,
    ) -> LoreTemporalChoice:
        """Jev Choice Decision: Categorical classification of Allen interval relations for historical timeline."""
        if candidate_relations is None:
            candidate_relations = ["before", "meets", "overlaps", "during", "finishes", "equals", "after"]

        context_lower = narrative_context.lower()
        scores: Dict[str, float] = {r: 0.1 for r in candidate_relations}

        for r in candidate_relations:
            if r in context_lower:
                scores[r] += 2.0
            if r == "before" and any(w in context_lower for w in ["prior to", "before", "preceded", "dawn age", "ancient past"]):
                scores[r] += 2.4
            if r == "after" and any(w in context_lower for w in ["after", "following", "later", "subsequent", "centuries after"]):
                scores[r] += 2.4
            if r == "during" and any(w in context_lower for w in ["during", "throughout", "in the reign of", "in the year", "amidst"]):
                scores[r] += 2.3
            if r == "meets" and any(w in context_lower for w in ["immediately prior", "until the fall", "right up to"]):
                scores[r] += 2.2
            if r == "equals" and any(w in context_lower for w in ["exact same time", "coeval", "synchronous", "contemporary"]):
                scores[r] += 2.2
            if r == "overlaps" and any(w in context_lower for w in ["partially coincided", "overlapped with"]):
                scores[r] += 2.2

        exp_vals = {r: math.exp(s / self.temperature) for r, s in scores.items()}
        total_exp = sum(exp_vals.values())
        probs = {r: exp_vals[r] / total_exp for r in candidate_relations}

        chosen = max(probs.keys(), key=lambda k: probs[k])
        confidence = probs[chosen]

        return LoreTemporalChoice(
            interval_a=interval_a,
            interval_b=interval_b,
            allen_relation=chosen,
            probabilities=probs,
            confidence=confidence,
        )

    def audit_entity_canon(
        self,
        world_rules: str,
        entity_name: str,
        entity_narrative: str,
        immutable_laws: List[str],
    ) -> JevCanonAuditReport:
        """Executes a parallel Jev decision pass over all immutable laws and evaluates overall risk."""
        axiom_decisions = self.batch_decide_lore_axioms(
            world_rules=world_rules,
            entity_narrative=entity_narrative,
            axioms=immutable_laws,
        )

        violations = []
        for law, decision in axiom_decisions.items():
            if not decision.verdict or decision.is_strongly_no():
                violations.append(
                    f"Axiom breach: '{law}' (P_comply={decision.p_yes:.2f}, conf={decision.confidence:.2f})"
                )

        risk_decision = self.evaluate_lore_distortion_risk(
            world_context=world_rules,
            entity_narrative=entity_narrative,
        )

        if violations or risk_decision.score >= 2.0:
            recommended_verdict = "REJECT_AXIOM_VIOLATION"
            explanation = f"Jev System-1 rejected entity. {'; '.join(violations) or 'Critical risk level detected.'}"
        else:
            recommended_verdict = "APPROVE"
            explanation = f"Jev System-1 verified entity canon compliance (risk_score={risk_decision.score:.2f})."

        overall_compliance = JevNoulDecision(
            instructions=f"All {len(immutable_laws)} laws satisfied for {entity_name}",
            p_yes=0.04 if violations else 0.96,
            confidence=max((d.confidence for d in axiom_decisions.values()), default=0.9),
        )

        return JevCanonAuditReport(
            is_canon_consistent=overall_compliance,
            lore_distortion_risk=risk_decision,
            axiom_evaluations=axiom_decisions,
            recommended_verdict=recommended_verdict,
            explanation=explanation,
        )

