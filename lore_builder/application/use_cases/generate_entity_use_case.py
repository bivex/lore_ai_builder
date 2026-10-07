import os
import json
from typing import Optional

from ..ports.inbound.generate_lore_port import GenerateLoreUseCasePort
from ..ports.outbound.memory_port import MemoryPort
from ..ports.outbound.resource_port import ResourceControllerPort
from ..ports.outbound.llm_port import LLMProviderPort
from ..ports.outbound.event_publisher_port import EventPublisherPort
from ..ports.inbound.audit_lore_port import AuditLoreUseCasePort
from ..dto.entity_dto import GenerateEntityCommand, EntityResponseDTO
from ...domain.model.aggregate import LoreEntityAggregate
from ...domain.model.value_objects import TimelinePoint, RelationType, CanonStatus
from ...domain.exceptions import LoreCanonConflictError


class GenerateEntityUseCase(GenerateLoreUseCasePort):
    """Orchestrates entity generation through memory retrieval, LLM inference under OS resource constraints, and canon audit."""

    def __init__(
        self,
        memory_port: MemoryPort,
        resource_controller: ResourceControllerPort,
        llm_provider: LLMProviderPort,
        event_publisher: EventPublisherPort,
        audit_use_case: AuditLoreUseCasePort,
    ):
        self.memory = memory_port
        self.resources = resource_controller
        self.llm = llm_provider
        self.publisher = event_publisher
        self.auditor = audit_use_case

    def execute(self, cmd: GenerateEntityCommand) -> EntityResponseDTO:
        session_name = f"lore_gen_{cmd.name.lower().replace(' ', '_')}"
        session_id = self.resources.create_session(
            session_name=session_name,
            max_memory_mb=512,
            cpu_cap_percent=80,
            auto_trim_idle=True,
        )

        try:
            # 1. Bind current process to OS Resource limits (JobObjects / Darwin QoS)
            self.resources.assign_process(session_id, os.getpid())

            # 2. Extract Context from Memory (L3 World Bible + L1 Facts)
            world_bible = self.memory.get_world_bible()
            relevant_facts = self.memory.search_canonical_facts(
                query=f"{cmd.name} {cmd.prompt_hint}", limit=5
            )

            facts_context = "\n".join(f"- {f.statement}" for f in relevant_facts) or "None recorded yet."
            allowed_relations = ", ".join(f"'{e.value}'" for e in RelationType)
            system_prompt = (
                f"{world_bible.render_prompt_context()}\n\n"
                f"RELEVANT CANON FACTS (L1):\n{facts_context}\n\n"
                "You are an expert worldbuilding chronicler. Output ONLY clean valid JSON with exact keys: "
                "\"summary\" (string), \"description\" (string), \"facts\" (list of strings), "
                f"\"relations\" (list of objects with 'target', 'type', 'context').\n"
                f"Allowed values for relation 'type': {allowed_relations}."
            )

            prompt = (
                f"Create a new {cmd.entity_type.value} named '{cmd.name}'.\n"
                f"Context details: {cmd.prompt_hint}\n"
                f"Era: {cmd.era or 'Mythic Age'}, Year: {cmd.year or 100}"
            )

            # 3. LLM Inference Phase — Apply OS Memory Compression Shield during idle wait
            with self.resources.memory_shield(session_id):
                raw_llm_response = self.llm.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.7,
                )

            # 4. Save Raw Output into L0 Conversation Memory
            self.memory.save_draft_conversation(
                session_id=session_name,
                prompt=prompt,
                response=raw_llm_response,
            )

            # 5. Parse Draft into Aggregate
            draft_data = self._parse_llm_json(raw_llm_response, cmd)
            timeline = TimelinePoint(year=cmd.year or 100, era=cmd.era or "First Age") if cmd.year else None

            entity = LoreEntityAggregate.create_draft(
                name=cmd.name,
                entity_type=cmd.entity_type,
                summary=draft_data.get("summary", f"{cmd.name} summary"),
                description=draft_data.get("description", raw_llm_response),
                timeline_point=timeline,
                session_id=session_name,
            )

            for fact_text in draft_data.get("facts", []):
                entity.add_fact(fact_text)

            for rel in draft_data.get("relations", []):
                rel_type = self._parse_relation_type(rel.get("type", "allied_with"))
                entity.add_relation(
                    target_name=rel.get("target", "Unknown"),
                    relation_type=rel_type,
                    context=rel.get("context"),
                )

            self.publisher.publish_all(entity.pull_events())

            # 6. Audit Phase — Freeze Generator process tree while auditing canon consistency
            with self.resources.frozen_scope(session_id):
                audit_result = self.auditor.execute(entity)

            if not audit_result.is_valid:
                raise LoreCanonConflictError(entity.name, audit_result.contradictions)

            # 7. Canon Write-Back: Commit L1 facts & Publish Wiki Knowledge page
            for fact in entity.facts:
                self.memory.commit_atomic_fact(fact)

            wiki_url = self.memory.publish_wiki_page(entity)

            # 8. Return response DTO
            return EntityResponseDTO(
                entity_id=entity.entity_id,
                name=entity.name,
                entity_type=entity.entity_type.value,
                summary=entity.summary,
                description=entity.description,
                status=entity.status.value,
                facts=[f.statement for f in entity.facts],
                relations=[
                    {"target": r.target_entity_name, "type": r.relation_type.value, "context": r.context or ""}
                    for r in entity.relations
                ],
                timeline=str(entity.timeline_point) if entity.timeline_point else None,
            )

        finally:
            self.resources.destroy_session(session_id)

    def _parse_llm_json(self, raw_text: str, cmd: GenerateEntityCommand) -> dict:
        # Clean markdown code blocks if present
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        try:
            data = json.loads(cleaned.strip())
        except Exception as e:
            raise ValueError(f"Strict LLM JSON parse failure for '{cmd.name}': {e}. Raw output: {raw_text}")

        if not isinstance(data, dict):
            raise ValueError(f"Strict LLM format failure: expected JSON object, got {type(data).__name__}")

        if "summary" not in data or "description" not in data:
            raise ValueError(
                f"Strict LLM format failure: missing 'summary' or 'description' in output: {data}"
            )

        return data

    def _parse_relation_type(self, raw_type: str) -> RelationType:
        raw_clean = raw_type.lower().strip()
        for member in RelationType:
            if member.value == raw_clean:
                return member

        # Normalization mapping for common synonyms
        synonyms = {
            "allied": RelationType.ALLIED_WITH,
            "ally": RelationType.ALLIED_WITH,
            "leader": RelationType.LEADER_OF,
            "rules": RelationType.LEADER_OF,
            "ruled": RelationType.LEADER_OF,
            "member": RelationType.MEMBER_OF,
            "enemy": RelationType.ENEMY_OF,
            "located": RelationType.LOCATED_IN,
            "location": RelationType.LOCATED_IN,
            "creator": RelationType.CREATED_BY,
            "created": RelationType.CREATED_BY,
            "created_by": RelationType.CREATED_BY,
            "possesses": RelationType.POSSESSES,
            "possess": RelationType.POSSESSES,
            "participated": RelationType.PARTICIPATED_IN,
            "cause": RelationType.CAUSE_OF,
        }
        if raw_clean in synonyms:
            return synonyms[raw_clean]

        raise ValueError(
            f"Invalid relation type '{raw_type}'. Allowed types: {[e.value for e in RelationType]}"
        )
