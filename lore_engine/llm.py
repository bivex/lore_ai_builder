import os
import json
import re
import logging
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

from .models import Entity, Relation, Task, WorldBible, EntityType

logger = logging.getLogger(__name__)


class LoreLLMClient:
    """Unified OpenAI-compatible LLM client supporting OpenRouter and Ollama with structured generation and repair."""

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

        if not self.use_mock:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
        else:
            self._client = None

    def generate_entity(self, task: Task, context_facts: str, world_bible: WorldBible) -> Entity:
        """Generates a complete lore entity with facts and outward relations."""
        if self.use_mock:
            return self._mock_generate(task, world_bible)

        type_hint = f"Тип сущности: {task.entity_type.value}" if task.entity_type else "Определи тип сущности сам (character, faction, location, historical_event, artifact)."
        system_prompt = (
            f"Ты — главный летописец вселенной '{world_bible.name}'.\n"
            f"КОСМОЛОГИЯ: {world_bible.cosmology}\n"
            f"НЕПРЕЛОЖНЫЕ ЗАКОНЫ МИРА (АКСИОМЫ):\n"
            + "\n".join(f"- {law}" for law in world_bible.immutable_laws) + "\n\n"
            f"ИЗВЕСТНЫЙ КОНТЕКСТ И ФАКТЫ МИРА:\n{context_facts}\n\n"
            "ТРЕБОВАНИЯ:\n"
            "1. Верни ИСКЛЮЧИТЕЛЬНО валидный JSON без лишнего текста.\n"
            "2. Соблюдай все непреложные законы мира (особенно цену магии и смертность).\n"
            "3. Укажи 2-3 атомарных факта с точным годом.\n"
            "4. В поле 'relations' укажи 1-3 логичные связи с другими сущностями мира (новые или существующие). "
            "Разрешенные типы связей: leader_of, allied_with, enemy_of, located_in, participated_in, cause_of, possesses, member_of.\n\n"
            "ФОРМАТ JSON:\n"
            "{\n"
            f'  "name": "{task.name}",\n'
            '  "entity_type": "character|faction|location|historical_event|artifact",\n'
            '  "summary": "Краткое саммари (1-2 предложения)",\n'
            '  "description": "Подробное художественное описание",\n'
            '  "era": "Первая Эпоха|Вторая Эпоха",\n'
            '  "year": 120,\n'
            '  "facts": ["Факт 1", "Факт 2"],\n'
            '  "relations": [{"target": "Имя Цели", "type": "enemy_of", "context": "Контекст связи"}]\n'
            "}"
        )

        user_prompt = (
            f"Создай сущность: '{task.name}'.\n"
            f"{type_hint}\n"
            f"Контекстная подсказка / происхождение: {task.hint or 'Первородная сущность мира'}\n"
            f"Глубина в графе: {task.depth}"
        )

        raw = self._call_llm(system_prompt, user_prompt)
        return self._parse_entity_json(raw, task.name)

    def repair_entity(self, entity: Entity, problems: List[str], context_facts: str, world_bible: WorldBible) -> Entity:
        """Self-healing reflection loop: repairs an entity that failed canon judge."""
        if self.use_mock:
            return self._mock_repair(entity, problems)

        system_prompt = (
            f"Ты — строгий редактор канона вселенной '{world_bible.name}'.\n"
            f"ЗАКОНЫ МИРА:\n" + "\n".join(f"- {l}" for l in world_bible.immutable_laws) + "\n\n"
            "Предыдущая версия сущности не прошла проверку канона. Твоя задача — исправить текст так, "
            "чтобы убрать все выявленные противоречия, сохранив суть и верность законам мира.\n"
            "Верни ИСКЛЮЧИТЕЛЬНО исправленный валидный JSON в той же структуре."
        )

        user_prompt = (
            f"Сущность: '{entity.name}'\n"
            f"Текущий JSON:\n{entity.model_dump_json(indent=2)}\n\n"
            "ПРОБЛЕМЫ И ЗАМЕЧАНИЯ СУДЬИ КАНОНА:\n"
            + "\n".join(f"- {p}" for p in problems) + "\n\n"
            "Исправь сущность, чтобы она строго соответствовала законам мира и замечаниям судьи."
        )

        raw = self._call_llm(system_prompt, user_prompt)
        return self._parse_entity_json(raw, entity.name)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        import time
        max_attempts = 3
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                    max_tokens=1500,
                )
                if resp and getattr(resp, "choices", None) and len(resp.choices) > 0:
                    choice = resp.choices[0]
                    if choice and getattr(choice, "message", None) and choice.message.content:
                        return choice.message.content

                logger.warning(f"Empty choices returned from LLM on attempt {attempt}/{max_attempts}")
            except Exception as e:
                last_error = e
                logger.warning(f"LLM API call attempt {attempt}/{max_attempts} failed: {e}")

            time.sleep(1.5 * attempt)

        raise RuntimeError(f"OpenRouter/LLM inference failure after {max_attempts} attempts: {last_error}")

    def _parse_entity_json(self, raw_text: str, expected_name: str) -> Entity:
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0]

        try:
            data = json.loads(cleaned.strip())
        except Exception as e:
            # Try to extract the first {...} block
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                raise ValueError(f"Failed to parse LLM JSON output for '{expected_name}': {e}. Raw: {raw_text[:200]}")

        # Ensure name consistency
        data["name"] = data.get("name") or expected_name

        # Parse relations safely
        clean_relations = []
        for r in data.get("relations", []):
            if isinstance(r, dict) and "target" in r and "type" in r:
                clean_relations.append(Relation(
                    target=str(r["target"]).strip(),
                    type=str(r.get("type", "allied_with")).lower().strip(),
                    context=str(r.get("context", "")).strip(),
                ))
        data["relations"] = clean_relations

        # Normalize entity type
        raw_type = str(data.get("entity_type", "character")).lower()
        valid_types = {e.value: e for e in EntityType}
        data["entity_type"] = valid_types.get(raw_type, EntityType.CHARACTER)

        return Entity(**data)

    def _mock_generate(self, task: Task, world_bible: WorldBible) -> Entity:
        """High-fidelity mock generator for testing without internet."""
        name = task.name
        hint = task.hint or ""
        name_lower = name.lower()

        if any(w in name_lower for w in ["клан", "орден", "дружина", "clan", "order"]):
            e_type = EntityType.FACTION
            if "волхв" in name_lower or "ashen" in name_lower:
                summary = f"{name} — древний орден северных чародеев и волхвов Нави."
                facts = [f"{name} основан в 150 году у ледяного разлома.", f"{name} ведет войну с Орденом Паладинов."]
                rels = [Relation(target="Орден Паладинов Рассвета", type="enemy_of", context="Священная вражда за земли")]
            elif "дружина" in name_lower:
                summary = f"{name} — рать витязей и защитников Порубежья."
                facts = [f"{name} сформирована воеводой в 110 году.", f"{name} держит оборону на Заставе Яви."]
                rels = [Relation(target="Застава Яви", type="located_in", context="Опорный пункт обороны")]
            else:
                summary = f"{name} — рыцарское братство защитников света."
                facts = [f"{name} воздвиг башни света в 160 году.", f"{name} отражает набеги Нави."]
                rels = [Relation(target="Древний Клан Волхвов", type="enemy_of", context="Борьба со стужей")]
        elif any(w in name_lower for w in ["война", "битва", "осада", "war", "battle"]):
            e_type = EntityType.HISTORICAL_EVENT
            summary = f"{name} — тридцатилетний конфликт между волхвами и паладинами."
            facts = [f"{name} началась в 200 году со штурма башен света."]
            rels = [
                Relation(target="Древний Клан Волхвов", type="participated_in", context="Атакующая сторона"),
                Relation(target="Орден Паладинов Рассвета", type="participated_in", context="Обороняющаяся сторона"),
            ]
        elif any(w in name_lower for w in ["пустоши", "застава", "врата", "рубеж", "wastes", "gate"]):
            e_type = EntityType.LOCATION
            summary = f"{name} — укрепленный рубеж или территория на границе Яви и Нави."
            facts = [f"{name} образовались в результате прорыва сил Нави."]
            rels = [
                Relation(target="Северная Дружина", type="located_in", context="Место несения дозора"),
                Relation(target="Морозные Пустоши", type="adjacent_to", context="Граничит со стужей"),
            ]
        else:
            e_type = EntityType.CHARACTER
            summary = f"{name} — {hint.split('.')[0] if hint else 'хранитель рубежей, верный древним законам'}."
            facts = [f"{name} пожертвовал частью жизненной силы ради защиты Яви в 115 году."]
            rels = [
                Relation(target="Северная Дружина", type="leader_of", context="Командует ратью"),
                Relation(target="Застава Яви", type="located_in", context="Несет дозор на рубеже"),
            ]

        return Entity(
            name=name,
            entity_type=e_type,
            summary=summary,
            description=f"{summary} Неукоснительно блюдет законы эквивалентной жертвы мира '{world_bible.name}'.",
            era="Первая Эпоха",
            year=115,
            facts=facts,
            relations=rels,
        )

    def _mock_repair(self, entity: Entity, problems: List[str]) -> Entity:
        """Removes violating phrases and adds sacrificial cost."""
        clean_desc = entity.description
        clean_desc = re.sub(r"(?:бессмертн\w*|вечн\w*)\s+(?:чародей|тиран|бог)", "смертный правитель", clean_desc, flags=re.IGNORECASE)
        clean_desc += " За сотворенные чары была принесена священная жертва жизненной силы согласно законам мира."

        clean_facts = [
            re.sub(r"без\s+жертв\w*", "ценой великой жертвы", f, flags=re.IGNORECASE)
            for f in entity.facts
        ]

        return Entity(
            name=entity.name,
            entity_type=entity.entity_type,
            summary=entity.summary.replace("бессмертный", "доблестный"),
            description=clean_desc,
            era=entity.era,
            year=entity.year,
            facts=clean_facts,
            relations=entity.relations,
        )
