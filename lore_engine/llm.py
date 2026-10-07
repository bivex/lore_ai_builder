import os
import json
import logging
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
import instructor
import json_repair
from openai import OpenAI

from .models import (
    Entity,
    Relation,
    RelationType,
    Task,
    WorldBible,
    EntityType,
    Violation,
    Verdict,
    AtomicFact,
    EntityFactsDraft,
    ProseVerification,
)

logger = logging.getLogger(__name__)


class LoreLLMClient:
    """Unified OpenAI-compatible LLM client supporting Two-Stage 'Facts-First -> Prose' generation,
    structured JSON validation, and self-healing reflection.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_mock: bool = False,
        timeout: float = 45.0,
    ):
        load_dotenv()
        self.use_mock = use_mock
        self.timeout = timeout

        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or "dummy-key"
        self.base_url = base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.model = model or os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

        self.mock_verdicts: Dict[str, Verdict] = {}
        self._mock_verdicts = self.mock_verdicts
        self.mock_prose_verifications: Dict[str, ProseVerification] = {}
        self._mock_prose_verifications = self.mock_prose_verifications

        if not self.use_mock:
            self._raw_client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
            self._client = instructor.from_openai(self._raw_client)
        else:
            self._raw_client = None
            self._client = None

    def set_mock_verdict(self, entity_name: str, verdict: Verdict) -> None:
        """Injects a predetermined mock Verdict for an entity (for tests/offline testing)."""
        self._mock_verdicts[entity_name.strip().casefold()] = verdict

    def set_mock_prose_verification(self, entity_name: str, verification: ProseVerification) -> None:
        """Injects a predetermined mock ProseVerification for an entity."""
        self._mock_prose_verifications[entity_name.strip().casefold()] = verification

    # =========================================================================
    # STAGE 1: FACTS-FIRST DRAFT GENERATION
    # =========================================================================

    def generate_facts_draft(self, task: Task, context_facts: str, world_bible: WorldBible) -> EntityFactsDraft:
        """Stage 1: Generates atomic verifiable facts and typed relations (Facts-first)."""
        if self.use_mock:
            return self._mock_generate_facts_draft(task, world_bible)

        eras_str = ", ".join(world_bible.eras) if getattr(world_bible, "eras", None) else "Первая Эпоха, Вторая Эпоха"
        type_hint = f"Тип сущности: {task.entity_type.value}" if task.entity_type else "Определи тип сущности сам (character, faction, location, historical_event, artifact)."
        system_prompt = (
            f"Ты — строгий архивариус и хронограф вселенной '{world_bible.name}'.\n"
            f"КОСМОЛОГИЯ: {world_bible.cosmology}\n"
            f"КАНОНИЧЕСКИЕ ЭПОХИ МИРА: {eras_str}\n"
            f"НЕПРЕЛОЖНЫЕ ЗАКОНЫ МИРА:\n"
            + "\n".join(f"- {law}" for law in world_bible.immutable_laws) + "\n\n"
            f"ИЗВЕСТНЫЙ КОНТЕКСТ И ФАКТЫ МИРА:\n{context_facts}\n\n"
            "ТРЕБОВАНИЯ К ФАКТАМ (ШАГ 1: АТОМАРНЫЕ ФАКТЫ):\n"
            "1. Верни ИСКЛЮЧИТЕЛЬНО валидный JSON схемы EntityFactsDraft.\n"
            f"2. Поле 'era' ДОЛЖНО быть строго одной из канонических эпох: {eras_str}.\n"
            "3. Сформулируй ровно 3-4 проверяемых атомарных факта с точным годом (числом) и эпохой.\n"
            "4. Для смертных персонажей (character) все факты ДОЛЖНЫ укладываться в естественную продолжительность жизни (не более 60-80 лет между событиями).\n"
            "5. В поле 'relations' укажи 1-3 логичные связи с соблюдением онтологии:\n"
            "   - leader_of / member_of: ТОЛЬКО персонаж -> фракция (character -> faction)\n"
            "   - participated_in: ТОЛЬКО участие в историческом событии (target: historical_event)\n"
            "   - located_in: ТОЛЬКО нахождение в локации (target: location)\n"
            "   - possesses: владение артефактом или локацией (source: character/faction -> target: artifact/location)\n"
            "   - predecessor_of / successor_of: ТОЛЬКО между сущностями одного типа\n"
            "   ВНИМАНИЕ: Для павших воевод и предшественников используй 'predecessor_of', а не 'enemy_of'!\n\n"
            "ФОРМАТ JSON:\n"
            "{\n"
            f'  "name": "{task.name}",\n'
            '  "entity_type": "character|faction|location|historical_event|artifact",\n'
            '  "era": "Вторая Эпоха",\n'
            '  "year": 325,\n'
            '  "facts": [\n'
            '    {\n'
            '      "year": 325,\n'
            '      "era": "Вторая Эпоха",\n'
            '      "statement": "325 год: Точное проверяемое утверждение события с соблюдением законов мира.",\n'
            '      "participants": ["Имя 1", "Имя 2"]\n'
            '    }\n'
            '  ],\n'
            '  "relations": [\n'
            '    {"target": "Цель", "type": "predecessor_of|allied_with|located_in", "context": "Контекст связи"}\n'
            '  ]\n'
            "}"
        )

        user_prompt = (
            f"Сформируй факты и связи для сущности: '{task.name}'.\n"
            f"{type_hint}\n"
            f"Контекстная подсказка: {task.hint or 'Первородная сущность мира'}\n"
            f"Глубина в графе: {task.depth}"
        )

        if self._client:
            try:
                draft: EntityFactsDraft = self._client.chat.completions.create(
                    model=self.model,
                    response_model=EntityFactsDraft,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_retries=2,
                )
                if not draft.name:
                    draft.name = task.name
                return draft
            except Exception as e:
                logger.warning(f"Instructor structured draft completion fallback to raw call: {e}")

        raw = self._call_llm(system_prompt, user_prompt)
        return self._parse_facts_draft_json(raw, task.name)

    def repair_facts_draft(
        self,
        draft: EntityFactsDraft,
        problems: List[str],
        context_facts: str,
        world_bible: WorldBible,
    ) -> EntityFactsDraft:
        """Repairs draft facts and relations that failed audit."""
        if self.use_mock:
            return self._mock_repair_facts_draft(draft, problems)

        system_prompt = (
            f"Ты — строгий редактор хроники вселенной '{world_bible.name}'.\n"
            f"ЗАКОНЫ МИРА:\n" + "\n".join(f"- {l}" for l in world_bible.immutable_laws) + "\n\n"
            "Черновик фактов сущности не прошёл проверку канона. Твоя задача — исправить факты и связи.\n"
            "Верни ИСКЛЮЧИТЕЛЬНО исправленный JSON схемы EntityFactsDraft."
        )

        user_prompt = (
            f"Сущность: '{draft.name}'\n"
            f"Текущий JSON черновика:\n{draft.model_dump_json(indent=2)}\n\n"
            "ЗАМЕЧАНИЯ АУДИТА:\n" + "\n".join(f"- {p}" for p in problems) + "\n\n"
            "Исправь факты, даты и типы связей в соответствии с замечаниями."
        )

        if self._client:
            try:
                repaired: EntityFactsDraft = self._client.chat.completions.create(
                    model=self.model,
                    response_model=EntityFactsDraft,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_retries=2,
                )
                if not repaired.name:
                    repaired.name = draft.name
                return repaired
            except Exception as e:
                logger.warning(f"Instructor repair completion fallback to raw call: {e}")

        raw = self._call_llm(system_prompt, user_prompt)
        return self._parse_facts_draft_json(raw, draft.name)

    # =========================================================================
    # STAGE 2: PROSE SYNTHESIS STRICTLY FROM ACCEPTED FACTS
    # =========================================================================

    def synthesize_prose(self, task: Task, draft: EntityFactsDraft, world_bible: WorldBible) -> Entity:
        """Stage 2: Synthesizes summary and description strictly derived from accepted facts."""
        if self.use_mock:
            return self._mock_synthesize_prose(task, draft, world_bible)

        facts_text = "\n".join(f"- {f.statement}" for f in draft.facts)
        rels_text = "\n".join(f"- [{r.type}] {r.target} ({r.context})" for r in draft.relations)

        system_prompt = (
            f"Ты — мастер художественной прозы и стиля вселенной '{world_bible.name}'.\n"
            "Твоя задача — написать краткое саммари и выразительное описание сущности СТРОГО на основе утверждённых фактов.\n\n"
            "УТВЕРЖДЁННЫЕ ФАКТЫ:\n"
            f"{facts_text}\n\n"
            "СВЯЗИ СУЩНОСТИ:\n"
            f"{rels_text}\n\n"
            "СТРОЖАЙШИЕ ПРАВИЛА:\n"
            "1. ЗАПРЕЩЕНО добавлять новые исторические факты, события, сражения, даты, числа или артефакты, которых нет в списке утверждённых фактов выше. Обобщай ТОЛЬКО то, что подтверждено.\n"
            "2. СТИЛЬ: Суровое славянское тёмное фэнтези (Явь, Навь, хлад, рунные заставы). СТРОГО ЗАПРЕЩЕНЫ техно-анахронизмы (никаких шестерёнок, механики, часовых устройств).\n"
            "3. ЯЗЫК: Безупречный литературный русский язык. Запрещены псевдо-славянские слова-галлюцинации (никаких 'очглавил', 'навистный хладост', 'молоточи удары').\n"
            "4. Верни ИСКЛЮЧИТЕЛЬНО валидный JSON:\n"
            "{\n"
            '  "summary": "Лаконичное саммари (1-2 предложения, строго обобщающее факты)",\n'
            '  "description": "Художественное описание (1-2 абзаца, строго опирающееся только на утверждённые факты)"\n'
            "}"
        )

        user_prompt = f"Напиши саммари и описание для '{draft.name}' ({draft.entity_type.value})."
        raw = self._call_llm(system_prompt, user_prompt)
        parsed = self._parse_json_dict(raw)

        summary = str(parsed.get("summary", "")).strip() or f"{draft.name} — защитник Порубежья."
        description = str(parsed.get("description", "")).strip() or summary

        return Entity(
            name=draft.name,
            entity_type=draft.entity_type,
            summary=summary,
            description=description,
            era=draft.era,
            year=draft.year,
            facts=[f.statement for f in draft.facts],
            atomic_facts=draft.facts,
            relations=draft.relations,
        )

    def generate_entity(self, task: Task, context_facts: str, world_bible: WorldBible) -> Entity:
        """High-level generator composing two-stage generation: Facts -> Prose."""
        draft = self.generate_facts_draft(task, context_facts, world_bible)
        return self.synthesize_prose(task, draft, world_bible)

    def repair_entity(self, entity: Entity, problems: List[str], context_facts: str, world_bible: WorldBible) -> Entity:
        """Backward-compatible repair fallback."""
        if self.use_mock:
            return self._mock_repair(entity, problems)

        # Convert to draft, repair, then re-synthesize prose
        facts_list = []
        for f in entity.facts:
            facts_list.append(AtomicFact(year=entity.year, era=entity.era, statement=f))
        draft = EntityFactsDraft(
            name=entity.name,
            entity_type=entity.entity_type,
            era=entity.era,
            year=entity.year,
            facts=facts_list,
            relations=entity.relations,
        )
        repaired_draft = self.repair_facts_draft(draft, problems, context_facts, world_bible)
        return self.synthesize_prose(Task(name=entity.name, entity_type=entity.entity_type), repaired_draft, world_bible)

    # =========================================================================
    # AUDIT VERDICT
    # =========================================================================

    def audit_entity(self, entity: Entity, world_bible: WorldBible) -> Verdict:
        """Structured LLM-Judge audit replacing brittle regular expressions."""
        if self.use_mock:
            return self._mock_audit(entity, world_bible)

        system_prompt = (
            f"Ты — строгий независимый аудитор и судья канона вселенной '{world_bible.name}'.\n"
            "НЕПРЕЛОЖНЫЕ ЗАКОНЫ МИРА (АКСИОМЫ):\n"
            + "\n".join(f"- {l}" for l in world_bible.immutable_laws) + "\n\n"
            "ПРАВИЛА ОЦЕНКИ:\n"
            "1. Нарушением считай ТОЛЬКО буквальное, прямое противоречие закону мира (например, персонаж обрёл истинное бессмертие, стал богом, или сотворил могущественную магию без жертвы жизненной силы).\n"
            "2. Метафоры ('бессмертная верность', 'вечная слава в песнях', 'неувядающая дружба') НЕ являются нарушением!\n"
            "3. Отрицания ('не стал бессмертным', 'никогда не претендовал на божественность') НЕ являются нарушением!\n"
            "4. Описание битв с бессмертными врагами ('сражался с бессмертными тварями Нави') НЕ является нарушением персонажа!\n"
            "5. Жертва ради блага других ('без ущерба для крестьян') НЕ является нарушением, если сам герой принёс жертву.\n"
            "6. Для каждого нарушения ОБЯЗАТЕЛЬНО укажи дословную аксиому, точную цитату из текста, объяснение и severity ('minor', 'severe', 'canon_breaking').\n"
            "7. Если текст каноничен и нарушений нет, верни violations: [].\n\n"
            "ФОРМАТ JSON:\n"
            "{\n"
            '  "is_valid": true,\n'
            '  "violations": [\n'
            '    {\n'
            '      "axiom": "Закон о смертности",\n'
            '      "quote": "Стал бессмертным богом",\n'
            '      "explanation": "Смертный обрел бессмертие вопреки аксиоме",\n'
            '      "severity": "canon_breaking"\n'
            '    }\n'
            '  ],\n'
            '  "needs_review": false\n'
            "}"
        )

        user_prompt = (
            f"ПРОВЕРЯЕМАЯ СУЩНОСТЬ: '{entity.name}' ({entity.entity_type.value})\n"
            f"Саммари: {entity.summary}\n"
            f"Описание: {entity.description}\n"
            f"Факты:\n" + "\n".join(f"- {f}" for f in entity.facts)
        )

        if self._client:
            try:
                verdict: Verdict = self._client.chat.completions.create(
                    model=self.model,
                    response_model=Verdict,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_retries=2,
                )
                return verdict
            except Exception as e:
                logger.warning(f"Instructor audit completion fallback to raw call: {e}")

        raw = self._call_llm(system_prompt, user_prompt)
        return self._parse_verdict_json(raw)

    def verify_prose_support(self, entity: Entity, world_bible: WorldBible) -> ProseVerification:
        """Dedicated LLM semantic pass checking that prose is grounded in facts and adheres to style."""
        if self.use_mock:
            name_cf = entity.name.strip().casefold()
            if name_cf in self._mock_prose_verifications:
                return self._mock_prose_verifications[name_cf]
            return ProseVerification(is_supported=True, unsupported_claims=[], style_issues=[])

        facts_text = "\n".join(f"- {f}" for f in entity.facts)
        system_prompt = (
            f"Ты — строгий логический верификатор канона вселенной '{world_bible.name}'.\n"
            "Твоя задача — проверить художественную прозу (саммари и описание) сущности на 2 критерия:\n"
            "1. Неподтверждённые утверждения: содержит ли проза НОВЫЕ исторические факты, числа, даты, события или артефакты, которых НЕТ в утверждённых фактах.\n"
            "2. Стилистические нарушения: содержит ли текст техно-анахронизмы (шестерёнки, механизмы, часы, паровые двигатели) или выдуманные псевдо-славянские слова-галлюцинации.\n\n"
            "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON схемы ProseVerification:\n"
            "{\n"
            '  "is_supported": true,\n'
            '  "unsupported_claims": [],\n'
            '  "style_issues": []\n'
            "}"
        )
        user_prompt = (
            f"СУЩНОСТЬ: '{entity.name}' ({entity.entity_type.value})\n"
            f"УТВЕРЖДЁННЫЕ ФАКТЫ:\n{facts_text}\n\n"
            f"ПРОВЕРЯЕМАЯ ПРОЗА:\n"
            f"Саммари: {entity.summary}\n"
            f"Описание: {entity.description}\n"
        )

        if self._client:
            try:
                res: ProseVerification = self._client.chat.completions.create(
                    model=self.model,
                    response_model=ProseVerification,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_retries=2,
                )
                return res
            except Exception as e:
                logger.warning(f"Instructor prose verification fallback to raw call: {e}")

        raw = self._call_llm(system_prompt, user_prompt)
        parsed = self._parse_json_dict(raw)
        return ProseVerification(
            is_supported=bool(parsed.get("is_supported", True)) and not parsed.get("unsupported_claims", []) and not parsed.get("style_issues", []),
            unsupported_claims=parsed.get("unsupported_claims", []),
            style_issues=parsed.get("style_issues", []),
        )

    # =========================================================================
    # CALLS & PARSERS
    # =========================================================================

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        import time
        max_attempts = 3
        last_error = None
        client_to_use = self._raw_client if self._raw_client is not None else self._client

        for attempt in range(1, max_attempts + 1):
            try:
                resp = client_to_use.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                    max_tokens=2500,
                )
                if resp and getattr(resp, "choices", None) and len(resp.choices) > 0:
                    choice = resp.choices[0]
                    msg = getattr(choice, "message", None)
                    if msg:
                        content = msg.content or getattr(msg, "reasoning", None) or ""
                        if content:
                            return content

                logger.warning(f"Empty choices returned from LLM on attempt {attempt}/{max_attempts}")
            except Exception as e:
                last_error = e
                logger.warning(f"LLM API call attempt {attempt}/{max_attempts} failed: {e}")

            time.sleep(1.5 * attempt)

        raise RuntimeError(f"OpenRouter/LLM inference failure after {max_attempts} attempts: {last_error}")

    def _parse_json_dict(self, raw_text: str) -> Dict[str, Any]:
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0]

        try:
            res = json_repair.loads(cleaned.strip())
            if isinstance(res, dict):
                return res
            if isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict):
                return res[0]
        except Exception:
            pass

        try:
            return json.loads(cleaned.strip())
        except Exception:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(cleaned[start:end+1])
                except Exception:
                    pass
            return {}

    def _parse_facts_draft_json(self, raw_text: str, expected_name: str) -> EntityFactsDraft:
        data = self._parse_json_dict(raw_text)
        data["name"] = data.get("name") or expected_name

        raw_type = str(data.get("entity_type", "character")).lower()
        valid_types = {e.value: e for e in EntityType}
        entity_type = valid_types.get(raw_type, EntityType.CHARACTER)

        raw_facts = data.get("facts", [])
        facts = []
        for rf in raw_facts:
            if isinstance(rf, dict):
                facts.append(AtomicFact(
                    year=int(rf.get("year", data.get("year", 100))),
                    era=str(rf.get("era", data.get("era", "Вторая Эпоха"))),
                    statement=str(rf.get("statement", "")),
                    participants=rf.get("participants", []),
                ))
            elif isinstance(rf, str):
                facts.append(AtomicFact(
                    year=int(data.get("year", 100)),
                    era=str(data.get("era", "Вторая Эпоха")),
                    statement=rf,
                    participants=[],
                ))

        relations = []
        for r in data.get("relations", []):
            if isinstance(r, dict) and "target" in r and "type" in r:
                relations.append(Relation(
                    target=str(r["target"]).strip(),
                    type=str(r.get("type", "allied_with")).lower().strip(),
                    context=str(r.get("context", "")).strip(),
                ))

        return EntityFactsDraft(
            name=data["name"],
            entity_type=entity_type,
            era=str(data.get("era", "Вторая Эпоха")),
            year=int(data.get("year", 100)),
            facts=facts,
            relations=relations,
        )

    def _parse_verdict_json(self, raw_text: str) -> Verdict:
        data = self._parse_json_dict(raw_text)
        violations_raw = data.get("violations", [])
        violations = []
        for v in violations_raw:
            if isinstance(v, dict) and "axiom" in v:
                violations.append(Violation(
                    axiom=str(v.get("axiom", "")),
                    quote=str(v.get("quote", "")),
                    explanation=str(v.get("explanation", "")),
                    severity=v.get("severity", "canon_breaking"),
                ))
        return Verdict(
            is_valid=len(violations) == 0,
            violations=violations,
            needs_review=bool(data.get("needs_review", False)),
        )

    # =========================================================================
    # MOCK IMPLEMENTATIONS FOR TESTS / OFFLINE
    # =========================================================================

    def _mock_generate_facts_draft(self, task: Task, world_bible: WorldBible) -> EntityFactsDraft:
        name = task.name
        name_lower = name.lower()

        if any(w in name_lower for w in ["клан", "орден", "дружина"]):
            e_type = EntityType.FACTION
            if "волхв" in name_lower:
                year = 150
                facts = [
                    AtomicFact(year=150, statement=f"{name} основан в 150 году у ледяного разлома."),
                    AtomicFact(year=160, statement=f"{name} ведет войну со светлыми орденами за контроль рубежей."),
                ]
                rels = [Relation(target="Орден Паладинов Рассвета", type="enemy_of", context="Священная вражда за земли")]
            elif "дружина" in name_lower:
                year = 312
                facts = [
                    AtomicFact(year=312, statement=f"{name} возглавлена воеводой Радомиром."),
                    AtomicFact(year=315, statement=f"{name} держит оборону у Врат Белокамня."),
                ]
                rels = [Relation(target="Застава Яви", type="located_in", context="Опорный пункт обороны")]
            else:
                year = 160
                facts = [
                    AtomicFact(year=160, statement=f"{name} воздвиг башни света."),
                    AtomicFact(year=170, statement=f"{name} отражает набеги Нави."),
                ]
                rels = [Relation(target="Древний Клан Волхвов", type="enemy_of", context="Борьба со стужей")]
        elif any(w in name_lower for w in ["пустоши", "застава", "врата", "рубеж"]):
            e_type = EntityType.LOCATION
            year = 110
            facts = [
                AtomicFact(year=110, statement=f"{name} основан как укрепленный рубеж на границе Яви и Нави."),
            ]
            rels = [
                Relation(target="Северная Дружина", type="created_by", context="Основана воинами дружины как опорный рубеж"),
                Relation(target="Морозные Пустоши", type="adjacent_to", context="Граничит со стужей"),
            ]
        else:
            e_type = EntityType.CHARACTER
            year = 312
            facts = [
                AtomicFact(year=312, statement=f"{name} избран верховным воеводой в 312 году."),
                AtomicFact(year=315, statement=f"{name} принес в жертву часть жизненной силы ради сдерживания Врат в 315 году."),
            ]
            rels = [
                Relation(target="Северная Дружина", type="leader_of", context="Командует ратью"),
                Relation(target="Застава Яви", type="located_in", context="Несет дозор на рубеже"),
            ]

        return EntityFactsDraft(
            name=name,
            entity_type=e_type,
            era="Первая Эпоха",
            year=year,
            facts=facts,
            relations=rels,
        )

    def _mock_repair_facts_draft(self, draft: EntityFactsDraft, problems: List[str]) -> EntityFactsDraft:
        clean_facts = [
            AtomicFact(year=f.year, era=f.era, statement=f.statement, participants=f.participants)
            for f in draft.facts
        ]
        return EntityFactsDraft(
            name=draft.name,
            entity_type=draft.entity_type,
            era=draft.era,
            year=draft.year,
            facts=clean_facts,
            relations=draft.relations,
        )

    def _mock_synthesize_prose(self, task: Task, draft: EntityFactsDraft, world_bible: WorldBible) -> Entity:
        summary = f"{draft.name} — {draft.entity_type.value} вселенной '{world_bible.name}'."
        description = f"{summary} Основные события: " + "; ".join(f.statement for f in draft.facts)
        return Entity(
            name=draft.name,
            entity_type=draft.entity_type,
            summary=summary,
            description=description,
            era=draft.era,
            year=draft.year,
            facts=[f.statement for f in draft.facts],
            atomic_facts=draft.facts,
            relations=draft.relations,
        )

    def _mock_generate(self, task: Task, world_bible: WorldBible) -> Entity:
        draft = self._mock_generate_facts_draft(task, world_bible)
        return self._mock_synthesize_prose(task, draft, world_bible)

    def _mock_repair(self, entity: Entity, problems: List[str]) -> Entity:
        return Entity(
            name=entity.name,
            entity_type=entity.entity_type,
            summary=entity.summary,
            description=entity.description,
            era=entity.era,
            year=entity.year,
            facts=entity.facts[:],
            relations=entity.relations[:],
        )

    def _mock_audit(self, entity: Entity, world_bible: WorldBible) -> Verdict:
        name_cf = entity.name.strip().casefold()
        if name_cf in self._mock_verdicts:
            return self._mock_verdicts[name_cf]
        return Verdict(
            is_valid=True,
            violations=[],
            needs_review=False,
        )
