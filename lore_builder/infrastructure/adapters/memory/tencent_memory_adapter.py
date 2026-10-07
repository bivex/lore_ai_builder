import sys
import os
import logging
from typing import List, Dict, Any, Optional

from ....application.ports.outbound.memory_port import MemoryPort
from ....domain.model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from ....domain.model.entity import LoreFact

logger = logging.getLogger(__name__)

# Add SDK path to sys.path
SDK_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../TencentDB-Agent-Memory/sdk/memory-core/python")
)
if SDK_PATH not in sys.path:
    sys.path.insert(0, SDK_PATH)

try:
    from tencentdb_agent_memory.v3 import MemoryClient
except ImportError:
    MemoryClient = None


class TencentAgentMemoryAdapter(MemoryPort):
    """Adapter integrating with TencentDB Agent Memory v3 Service (L0-L3 & Knowledge)."""

    def __init__(
        self,
        endpoint: str = "http://localhost:8080",
        api_key: str = "test-key",
        service_id: str = "lore-service",
        team_id: str = "lore-team",
        agent_id: str = "lore-architect",
        user_id: str = "author-1",
    ):
        self.endpoint = endpoint
        self.team_id = team_id
        self.agent_id = agent_id
        self.user_id = user_id
        self._client: Optional[Any] = None

        if MemoryClient is not None:
            try:
                self._client = MemoryClient(
                    endpoint=endpoint,
                    api_key=api_key,
                    service_id=service_id,
                    team_id=team_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"Could not connect to live TencentDB memory endpoint ({endpoint}): {e}")

    def get_world_bible(self) -> WorldBibleAggregate:
        if self._client:
            try:
                res = self._client.read_core()
                content = res.get("data", {}).get("content", "")
                if content:
                    return WorldBibleAggregate(
                        world_id="tencent_canon",
                        name="World Bible",
                        cosmology=content,
                        immutable_laws=["Extract from L3 Core"],
                    )
            except Exception as e:
                logger.error(f"Failed to read L3 core from memory service: {e}")

        return WorldBibleAggregate(
            world_id="default_world",
            name="Aethelgard Core",
            cosmology="A fractured plane bound by ancient ley lines.",
            immutable_laws=["Magic demands blood or vitality", "Mortals cannot bypass death without severe corruption"],
        )

    def save_world_bible(self, bible: WorldBibleAggregate) -> None:
        if self._client:
            try:
                content = bible.render_prompt_context()
                self._client.write_core(content=content)
            except Exception as e:
                logger.error(f"Failed to write L3 core: {e}")

    def search_canonical_facts(self, query: str, limit: int = 5) -> List[LoreFact]:
        if self._client:
            try:
                res = self._client.search_atomic(query=query, limit=limit)
                items = res.get("data", {}).get("items", [])
                facts = []
                for item in items:
                    facts.append(
                        LoreFact(
                            fact_id=item.get("id", "fact"),
                            entity_name=item.get("title", "Canon Fact"),
                            statement=item.get("content", ""),
                            tags=item.get("tags", []),
                        )
                    )
                return facts
            except Exception as e:
                logger.error(f"Failed to search L1 atomic facts: {e}")
        return []

    def commit_atomic_fact(self, fact: LoreFact) -> None:
        if self._client:
            try:
                self._client.update_atomic(
                    id=fact.fact_id,
                    content=fact.statement,
                    background=f"Entity: {fact.entity_name}, Tags: {','.join(fact.tags)}",
                )
            except Exception as e:
                logger.error(f"Failed to commit L1 fact: {e}")

    def save_draft_conversation(self, session_id: str, prompt: str, response: str) -> None:
        if self._client:
            try:
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": response},
                ]
                self._client.add_conversation(session_id=session_id, messages=messages)
            except Exception as e:
                logger.error(f"Failed to save L0 conversation: {e}")

    def publish_wiki_page(self, entity: LoreEntityAggregate) -> str:
        # In full deployment, calls MemoryKnowledge /v3/wiki/page/create endpoint
        return f"/v3/wiki/{entity.entity_id}"

    def get_entity_wiki_graph(self, entity_name: str) -> Dict[str, Any]:
        return {"node": entity_name, "connected": []}
