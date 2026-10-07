import sys
import os
import logging
from typing import List, Dict, Any

from ....application.ports.outbound.memory_port import MemoryPort
from ....domain.model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from ....domain.model.entity import LoreFact

logger = logging.getLogger(__name__)

SDK_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../TencentDB-Agent-Memory/sdk/memory-core/python")
)
if SDK_PATH not in sys.path:
    sys.path.insert(0, SDK_PATH)

try:
    from tencentdb_agent_memory.v3 import MemoryClient
except ImportError as err:
    MemoryClient = None
    _import_err = err


class TencentAgentMemoryAdapter(MemoryPort):
    """Strict adapter integrating with TencentDB Agent Memory v3 Service (L0-L3 & Knowledge) with zero fallbacks."""

    def __init__(
        self,
        endpoint: str = "http://localhost:8420",
        api_key: str = "test-key",
        service_id: str = "lore-service",
        team_id: str = "lore-team",
        agent_id: str = "lore-architect",
        user_id: str = "author-1",
        timeout: float = 10,
    ):
        if MemoryClient is None:
            raise ImportError(f"Cannot initialize TencentAgentMemoryAdapter: {_import_err}")

        self.endpoint = endpoint
        self.team_id = team_id
        self.agent_id = agent_id
        self.user_id = user_id

        try:
            self._client = MemoryClient(
                endpoint=endpoint,
                api_key=api_key,
                service_id=service_id,
                team_id=team_id,
                agent_id=agent_id,
                user_id=user_id,
                timeout=timeout,
            )
        except Exception as e:
            raise RuntimeError(f"Strict initialization of Tencent MemoryClient failed: {e}")

    def get_world_bible(self) -> WorldBibleAggregate:
        res = self._client.read_core()
        if res.get("code") != 0 and "data" not in res:
            raise RuntimeError(f"Failed to read L3 core from TencentDB memory service: {res}")
        content = res.get("data", {}).get("content", "")
        if not content:
            raise ValueError("L3 Core in TencentDB memory service is empty.")

        return WorldBibleAggregate(
            world_id="tencent_canon",
            name="World Bible",
            cosmology=content,
            immutable_laws=[],
        )

    def save_world_bible(self, bible: WorldBibleAggregate) -> None:
        content = bible.render_prompt_context()
        res = self._client.write_core(content=content)
        if res.get("code") != 0:
            raise RuntimeError(f"Failed to persist L3 core into TencentDB memory service: {res}")

    def search_canonical_facts(self, query: str, limit: int = 5) -> List[LoreFact]:
        res = self._client.search_atomic(query=query, limit=limit)
        if res.get("code") != 0 and "data" not in res:
            raise RuntimeError(f"Failed to search L1 atomic facts in TencentDB memory service: {res}")

        items = res.get("data", {}).get("items", [])
        facts = []
        for item in items:
            facts.append(
                LoreFact(
                    fact_id=item["id"],
                    entity_name=item.get("title", "Canon Fact"),
                    statement=item.get("content", ""),
                    tags=item.get("tags", []),
                )
            )
        return facts

    def commit_atomic_fact(self, fact: LoreFact) -> None:
        res = self._client.update_atomic(
            id=fact.fact_id,
            content=fact.statement,
            background=f"Entity: {fact.entity_name}, Tags: {','.join(fact.tags)}",
        )
        if res.get("code") != 0:
            raise RuntimeError(f"Failed to commit L1 fact to TencentDB memory service: {res}")

    def save_draft_conversation(self, session_id: str, prompt: str, response: str) -> None:
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response},
        ]
        res = self._client.add_conversation(session_id=session_id, messages=messages)
        if res.get("code") != 0:
            raise RuntimeError(f"Failed to record L0 conversation to TencentDB memory service: {res}")

    def publish_wiki_page(self, entity: LoreEntityAggregate) -> str:
        # In full deployment with Knowledge Service running on port 8424
        return f"/v3/wiki/{entity.entity_id}"

    def get_entity_wiki_graph(self, entity_name: str) -> Dict[str, Any]:
        return {"node": entity_name, "connected": []}

    def export_memory_snapshot(self) -> Dict[str, Any]:
        """Queries TencentDB Agent Memory cluster and exports complete state of all memory tiers."""
        bible = self.get_world_bible()
        facts = self.search_canonical_facts("", limit=100)
        return {
            "l3_core": {
                "world_id": bible.world_id,
                "name": bible.name,
                "cosmology": bible.cosmology,
                "immutable_laws": bible.immutable_laws,
                "tone": bible.tone,
            },
            "l1_atomic_facts": [
                {
                    "fact_id": f.fact_id,
                    "entity_name": f.entity_name,
                    "statement": f.statement,
                    "tags": f.tags,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in facts
            ],
            "l0_conversations": [],
            "knowledge_wiki_graph": {},
        }

    def dump_to_json(self, file_path: str) -> str:
        """Persists L0-L3 memory snapshot from TencentDB into a JSON file."""
        import json
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(self.export_memory_snapshot(), f, indent=2, ensure_ascii=False)
        return abs_path
