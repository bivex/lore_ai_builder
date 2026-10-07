import re
from typing import List
from .models import Entity, WorldBible


class LoreJudge:
    """Audits generated entities against World Bible immutable axioms and temporal causal rules."""

    @staticmethod
    def _is_true_mortality_violation(text: str) -> bool:
        """Distinguishes genuine claims of personal immortality from metaphorical glory or slaying foes."""
        # Strip benign metaphorical phrases
        cleaned = re.sub(
            r"\b(?:undying|immortal)\s+(?:loyalty|devotion|love|friendship|gratitude|respect|oath|vow|memory|legacy|renown|glory|verse|poetry|words|fame|deeds|art)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:бессмертн\w*|вечн\w*|неувядающ\w*)\s+(?:верност\w*|преданност\w*|любв\w*|дружб\w*|благодарност\w*|памят\w*|наследи\w*|слав\w*|подвиг\w*|клятв\w*|обет\w*|слов\w*|песн\w*)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        # Strip slaying/fighting immortal foes
        cleaned = re.sub(
            r"\b(?:fought|slayed|hunted|battled|opposed|defended\s+against|banished|survived)\s+(?:the\s+|an?\s+)?(?:immortal|undying)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:сражал\w*|воевал\w*|убил\w*|сверг\w*|изгнал\w*|победил\w*|противостоял\w*|защищал\w*)\s+(?:\w+\s+)?(?:бессмертн\w*)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        # Strip negations
        cleaned = re.sub(
            r"\b(?:not|never|refused|denied|without\s+being)\s+(?:an?\s+)?(?:immortal|undying|divinity)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:не\s+был|не\s+стал|никогда\s+не|отказал\w*\s+от|без\s+того\s+чтобы\s+стать)\s+(?:бессмертн\w*|божеств\w*)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

        violations = [
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
        return any(re.search(pat, cleaned, flags=re.IGNORECASE) for pat in violations)

    @staticmethod
    def _is_true_sacrifice_violation(text: str) -> bool:
        """Detects magic without price or sacrifice."""
        has_sacrifice = bool(
            re.search(r"\b(?:sacrificing|sacrificed|gave\s+up|paid\s+with|burnt|lost\s+his|lost\s+her)\b", text, flags=re.IGNORECASE)
            or re.search(r"(?:пожертвова\w*|отдал\w*\s+жизнь|заплатил\w*\s+кровью|прин[её]с\w*\s+в\s+жертву|отдал\w*\s+часть)", text, flags=re.IGNORECASE)
        )
        if has_sacrifice and not re.search(r"(?:\b(?:infinite|unlimited)\s+(?:magic|mana|spells?)\s+without\s+sacrifice\b|бесконечн\w*\s+маги\w*\s+без\s+жертв\w*)", text, flags=re.IGNORECASE):
            return False

        # Strip beneficiaries ("without cost to villagers")
        cleaned = re.sub(
            r"\b(?:without|at\s+no)\s+(?:cost|sacrifice)\s+to\s+(?:the|his|her|their|people|villagers|citizens|realm)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"без\s+(?:платы|жертв\w*|ущерба)\s+(?:для\s+)?(?:крестьян|народа|людей|жителей|земель|других)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

        violations = [
            r"\b(?:cast|casting|channeled|wielded|performed)\s+(?:magic|spells?)\s+(?:without|with\s+no)\s+(?:cost|sacrifice|price)\b",
            r"\b(?:magic|spells?)\s+without\s+(?:cost|sacrifice)\b",
            r"\b(?:infinite|unlimited)\s+(?:magic|mana|spells?)\s+(?:without|with\s+no)\s+(?:cost|sacrifice)\b",
            r"\bcast\s+infinite\s+magic\b",
            r"(?:творил|сотворил|использовал|применял|колдовал|кастовал)\s+(?:магию|заклинания|чары)\s+без\s+(?:жертв\w*|платы|цены)",
            r"(?:магия|колдовство|чары)\s+без\s+(?:жертв\w*|платы|цены)",
            r"бесконечн\w*\s+(?:маги\w*|сил\w*|чар\w*)\s+без\s+(?:жертв\w*|платы|цены)",
        ]
        return any(re.search(pat, cleaned, flags=re.IGNORECASE) for pat in violations)

    def audit(self, entity: Entity, world_bible: WorldBible, context: str = "") -> List[str]:
        """Audits the proposed entity against World Bible laws. Returns actionable problems for repair."""
        problems: List[str] = []
        entity_text = f"{entity.summary} {entity.description} {' '.join(entity.facts)}".lower()

        # 1. Check against immutable laws
        for law in world_bible.immutable_laws:
            law_lower = law.lower()

            # Mortality axiom
            if any(k in law_lower for k in ["mortal", "divinity", "смертн", "бессмерт", "божеств"]):
                if self._is_true_mortality_violation(entity_text):
                    problems.append(
                        f"Нарушение закона о смертности ('{law}'): Сущность утверждает бессмертие или божественность. "
                        "Исправьте описание: смертные персонажи не могут быть бессмертными или истинными богами."
                    )

            # Sacrifice / Conservation axiom
            if any(k in law_lower for k in ["sacrifice", "жертв", "плат", "сохранения чар"]):
                if self._is_true_sacrifice_violation(entity_text):
                    problems.append(
                        f"Нарушение закона эквивалентной жертвы ('{law}'): Магия использована без платы или жертвы. "
                        "Исправьте: укажите, какую цену, жизненную силу или жертву сущность отдала за использование чар."
                    )

            # Void rift axiom
            if any(k in law_lower for k in ["cannot be sealed", "не могут быть запечатаны", "врата нави"]):
                if re.search(r"(?:навсегда|навечно|полностью)\s+(?:запечатал|закрыл)\s+(?:врата|разлом)", entity_text):
                    problems.append(
                        f"Нарушение закона о Вратах Нави ('{law}'): Врата нельзя запечатать навсегда, их можно лишь сдерживать."
                    )

        # 2. Self-relations check
        for rel in entity.relations:
            if rel.target.lower().strip() == entity.name.lower().strip():
                problems.append(f"Сущность не может ссылаться сама на себя в связях ({rel.type} -> {rel.target}).")

        # 3. Empty facts or summary
        if len(entity.facts) == 0:
            problems.append("Сущность должна содержать хотя бы 1-2 конкретных атомарных факта с указанием эпохи или года.")

        return problems
