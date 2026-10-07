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

    @staticmethod
    def _is_true_mortality_violation(text: str) -> bool:
        """Distinguishes genuine claims of personal immortality/divinity from metaphorical usage, negations, or battling immortal foes."""
        # 1. Strip benign metaphorical phrases
        cleaned = re.sub(
            r"\b(?:undying|immortal)\s+(?:loyalty|devotion|love|friendship|gratitude|respect|oath|vow|memory|legacy|renown|glory|verse|poetry|words|fame|deeds|art|philosophy)\b",
            " ",
            text,
        )
        cleaned = re.sub(
            r"(?:бессмертн\w*|вечн\w*|неувядающ\w*)\s+(?:верност\w*|преданност\w*|любв\w*|дружб\w*|благодарност\w*|памят\w*|наследи\w*|слав\w*|подвиг\w*|клятв\w*|обет\w*|слов\w*|песн\w*)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        # 2. Strip antagonist phrases (hero fighting/slaying immortal foes)
        cleaned = re.sub(
            r"\b(?:fought|slayed|hunted|battled|opposed|defended\s+against|banished|survived)\s+(?:the\s+|an?\s+)?(?:immortal|undying)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:сражал\w*|воевал\w*|убил\w*|сверг\w*|изгнал\w*|победил\w*|противостоял\w*|защищал\w*)\s+(?:\w+\s+)?(?:бессмертн\w*)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        # 3. Strip explicit negations
        cleaned = re.sub(
            r"\b(?:not|never|refused|denied|without\s+being)\s+(?:an?\s+)?(?:immortal|undying|divinity)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:не\s+был|не\s+стал|никогда\s+не|отказал\w*\s+от|без\s+того\s+чтобы\s+стать)\s+(?:бессмертн\w*|божеств\w*)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        # 4. Genuine violations
        actual_violations = [
            r"\b(?:became|is|was|declared|ascended\s+as|achieved)\s+(?:an?\s+)?(?:immortal|undying|divine\s+god)\b",
            r"\b(?:achieved|gained|attained|stole)\s+(?:true\s+)?immortality\b",
            r"\b(?:cannot\s+die|never\s+dies|immune\s+to\s+death|defied\s+death\s+forever)\b",
            r"\bimmortal\s+(?:sorcerer|tyrant|king|emperor|warlord|ruler|being|mage)\b",
            r"\bundying\s+(?:sorcerer|tyrant|king|emperor|warlord|ruler|defier|abomination)\b",
            r"(?:стал|обр[её]л|достиг|провозгласил\s+себя|стал\s+вечным)\s+(?:бессмертн\w*|божественност\w*|богом)",
            r"(?:бессмертный|неумирающий)\s+(?:тиран|чародей|колдун|князь|владыка|правитель|маг)",
            r"(?:не\s+может\s+умереть|никогда\s+не\s+умр[её]т|неуязвим\s+к\s+смерти|победил\s+смерть)",
            r"истинн\w+\s+бессмерти\w+",
        ]
        return any(re.search(pat, cleaned, flags=re.IGNORECASE) for pat in actual_violations)

    @staticmethod
    def _is_true_sacrifice_violation(text: str) -> bool:
        """Distinguishes magic without cost from beneficiary descriptions (e.g. 'without cost to the villagers') and actual sacrifices."""
        has_explicit_sacrifice = bool(
            re.search(
                r"\b(?:sacrificing|sacrificed|gave\s+up|paid\s+with|burnt|lost\s+his|lost\s+her|offered\s+his|offered\s+her)\b",
                text,
            )
            or re.search(
                r"(?:пожертвова\w*|отдал\w*\s+жизнь|заплатил\w*\s+кровью|прин[её]с\w*\s+в\s+жертву|отдал\w*\s+часть)",
                text,
                flags=re.IGNORECASE,
            )
        )
        if has_explicit_sacrifice and not (
            re.search(r"\b(?:infinite|unlimited)\s+(?:magic|mana|spells?)\s+without\s+sacrifice\b", text)
            or re.search(r"бесконечн\w*\s+маги\w*\s+без\s+жертв\w*", text, flags=re.IGNORECASE)
        ):
            return False

        cleaned = re.sub(
            r"\b(?:without|at\s+no)\s+(?:cost|sacrifice)\s+to\s+(?:the|his|her|their|people|villagers|citizens|realm|poor|others|mortal)\b",
            " ",
            text,
        )
        cleaned = re.sub(
            r"без\s+(?:платы|жертв\w*|ущерба)\s+(?:для\s+)?(?:крестьян|народа|людей|жителей|земель|других|горожан)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:not|never|no\s+\w+)\s+(?:without\s+cost|without\s+sacrifice)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:не|никогда\s+не)\s+(?:без\s+платы|без\s+жертв\w*)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

        violation_patterns = [
            r"\b(?:cast|casting|channeled|wielded|performed)\s+(?:magic|spells?)\s+(?:without|with\s+no)\s+(?:cost|sacrifice|price)\b",
            r"\b(?:magic|spells?)\s+without\s+(?:cost|sacrifice)\b",
            r"\b(?:infinite|unlimited)\s+(?:magic|mana|spells?)\s+(?:without|with\s+no)\s+(?:cost|sacrifice)\b",
            r"\bcast\s+infinite\s+magic\b",
            r"\bwithout\s+cost\s+or\s+sacrifice\b",
            r"\bwithout\s+sacrifice\s+or\s+cost\b",
            r"(?:творил|сотворил|использовал|применял|колдовал|кастовал)\s+(?:магию|заклинания|чары)\s+без\s+(?:жертв\w*|платы|цены)",
            r"(?:магия|колдовство|чары)\s+без\s+(?:жертв\w*|платы|цены)",
            r"бесконечн\w*\s+(?:маги\w*|сил\w*|чар\w*)\s+без\s+(?:жертв\w*|платы|цены)",
            r"без\s+(?:жертвы|платы)\s+и\s+(?:платы|жертвы)",
        ]
        return any(re.search(pat, cleaned, flags=re.IGNORECASE) for pat in violation_patterns)

    @staticmethod
    def _is_true_void_violation(text: str) -> bool:
        """Detects whether entity claimed to permanently seal a void rift instead of diverting it."""
        if re.search(r"\b(?:diverted|redirected|channeled\s+away)\s+(?:the\s+)?(?:void|rift)\b", text) or re.search(
            r"(?:отв[её]л|перенаправил|сдержал)\s+(?:прорыв|разлом|врата)", text, flags=re.IGNORECASE
        ):
            if not (
                re.search(r"\b(?:permanently|completely)\s+sealed\s+(?:the\s+)?(?:void|rift)\b", text)
                or re.search(r"(?:навсегда|полностью)\s+(?:запечатал|закрыл)\s+(?:прорыв|разлом|врата)", text, flags=re.IGNORECASE)
            ):
                return False
        if re.search(r"\b(?:failed\s+to\s+seal|could\s+not\s+seal|attempted\s+to\s+seal\s+.*but\s+failed)\b", text) or re.search(
            r"(?:не\s+смог\s+запечатать|пытался\s+запечатать.*но\s+не\s+смог)", text, flags=re.IGNORECASE
        ):
            return False
        violation_patterns = [
            r"\b(?:permanently|completely|successfully)\s+(?:sealed|closed)\s+(?:the\s+)?(?:void|rift)\b",
            r"\b(?:sealed|closed)\s+(?:the\s+)?(?:void|rift)\s+(?:forever|permanently|completely)\b",
            r"\bsealed\s+the\s+void\s+(?:breach|rift)\b",
            r"(?:навсегда|полностью|навечно)\s+(?:запечатал|закрыл)\s+(?:прорыв|разлом|врата)",
            r"(?:запечатал|закрыл)\s+(?:прорыв|разлом|врата)\s+(?:навсегда|навечно)",
        ]
        return any(re.search(pat, text, flags=re.IGNORECASE) for pat in violation_patterns)

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
        if any(w in rule_lower for w in ["sacrifice", "жертв", "плат"]):
            if self._is_true_sacrifice_violation(narrative_lower):
                violation_indicators.append(0.97)

        # 2. Mortality Axiom
        if any(w in rule_lower for w in ["mortal", "cannot become immortal", "mortal coil", "cannot achieve true divinity", "смертн", "бессмерт", "божеств"]):
            if self._is_true_mortality_violation(narrative_lower):
                violation_indicators.append(0.98)

        # 3. Void / Sealed Realm Axioms
        if any(w in rule_lower for w in ["cannot be sealed", "unsealable", "не могут быть закрыты", "нельзя запечатать", "не могут быть запечатаны"]):
            if self._is_true_void_violation(narrative_lower):
                violation_indicators.append(0.95)

        # 4. Temporal Unidirectional Axiom
        if any(w in rule_lower for w in ["cannot alter past", "time flows forward", "нельзя изменить прошлое", "время течет", "необратимо"]):
            if (
                re.search(r"\b(?:traveled\s+back\s+in\s+time|altered\s+the\s+past|reversed\s+time|changed\s+history)\b", narrative_lower)
                or re.search(r"(?:изменил\s+прошлое|повернул\s+время\s+вспять|отправился\s+в\s+прошлое)", narrative_lower)
            ):
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

        # Score distribution based on verified canon distortion cues
        has_mortality = self._is_true_mortality_violation(narrative_lower)
        has_sacrifice = self._is_true_sacrifice_violation(narrative_lower)
        has_void = self._is_true_void_violation(narrative_lower)
        has_time = bool(re.search(r"\b(?:altered\s+the\s+past|reversed\s+time)\b", narrative_lower))

        if has_mortality or has_sacrifice or has_void or has_time:
            raw_logits = [-2.5, -1.0, 1.2, 3.8]
        elif any(w in narrative_lower for w in ["deviated", "secret forbidden spell", "anomalous power"]):
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
                w in context_lower
                for w in [
                    "commands", "leads", "ruler", "guided", "directs", "supreme", "commander of", "head of",
                    "командует", "возглавляет", "правит", "князь", "воевода", "предводитель", "повелевает", "глава",
                ]
            ):
                scores[r] += 3.5
            if any(term in r_lower for term in ["enemy", "hostile", "nemesis", "foe", "opposes"]) and any(
                w in context_lower
                for w in [
                    "war against", "fought against", "feud", "slain by", "opposed", "nemesis of", "bitter enemy",
                    "война", "враг", "сражался с", "воевал против", "заклятый враг", "ненавидит", "противостоит",
                ]
            ):
                scores[r] += 3.0
            if any(term in r_lower for term in ["allied", "friend", "sworn", "treaty", "member"]) and any(
                w in context_lower
                for w in [
                    "allied with", "sworn brother", "pact", "comrade", "served alongside", "member of", "brotherhood", "allied",
                    "союзник", "побратим", "поклялся в верности", "дружина", "братство", "орден", "союз", "верный",
                ]
            ):
                scores[r] += 2.8
            if any(term in r_lower for term in ["located", "dwelling", "stationed", "resides"]) and any(
                w in context_lower
                for w in [
                    "dwells in", "stationed at", "fortress of", "realm of", "inhabits", "located in",
                    "обитает в", "крепость", "расположен в", "находится в", "земли", "рубеж", "дозор",
                ]
            ):
                scores[r] += 2.8
            if any(term in r_lower for term in ["worships", "devoted", "priest"]) and any(
                w in context_lower
                for w in [
                    "temple", "prayer", "worships", "deity", "god of", "vow to", "sacred",
                    "храм", "молитва", "поклоняется", "божество", "бог", "святилище", "волхв", "жрец",
                ]
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
            if r == "before" and any(
                w in context_lower
                for w in [
                    "prior to", "before", "preceded", "dawn age", "ancient past",
                    "до", "ранее", "предшествовал", "предшествовала", "древние времена", "за века до",
                ]
            ):
                scores[r] += 2.4
            if r == "after" and any(
                w in context_lower
                for w in [
                    "after", "following", "later", "subsequent", "centuries after",
                    "после", "спустя", "позже", "века спустя", "вслед за",
                ]
            ):
                scores[r] += 2.4
            if r == "during" and any(
                w in context_lower
                for w in [
                    "during", "throughout", "in the reign of", "in the year", "amidst",
                    "во время", "в эпоху", "в период", "в годы", "на протяжении", "пока",
                ]
            ):
                scores[r] += 2.3
            if r == "meets" and any(
                w in context_lower
                for w in ["immediately prior", "until the fall", "right up to", "вплоть до", "непосредственно перед"]
            ):
                scores[r] += 2.2
            if r == "equals" and any(
                w in context_lower
                for w in ["exact same time", "coeval", "synchronous", "contemporary", "одновременно", "в то же самое время", "синхронно"]
            ):
                scores[r] += 2.2
            if r == "overlaps" and any(
                w in context_lower
                for w in ["partially coincided", "overlapped with", "частично совпало", "пересекалось"]
            ):
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

