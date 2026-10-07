from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from ....application.ports.outbound.memory_port import MemoryPort
from ....domain.model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from ....domain.model.entity import LoreFact


class InMemoryLoreMemoryAdapter(MemoryPort):
    """High-fidelity In-Memory adapter for testing, local offline development, and fallback."""

    def __init__(self, world_bible: Optional[WorldBibleAggregate] = None):
        self._bible = world_bible or WorldBibleAggregate(
            world_id="aethelgard_default",
            name="Aethelgard",
            cosmology="A fractured plane orbiting a dying stellar core, bound by the Ley Lines.",
            immutable_laws=[
                "Magic demands an equal sacrifice of vitality (No free energy)",
                "Mortals cannot achieve true divinity without burning their mortal shell",
                "The Void Rifts cannot be sealed, only diverted",
            ],
            tone="Dark High Fantasy",
        )
        self._facts: Dict[str, LoreFact] = {}
        self._conversations: List[Dict[str, Any]] = []
        self._wiki_pages: Dict[str, Dict[str, Any]] = {}

    def get_world_bible(self) -> WorldBibleAggregate:
        return self._bible

    def save_world_bible(self, bible: WorldBibleAggregate) -> None:
        self._bible = bible

    def search_canonical_facts(self, query: str, limit: int = 5) -> List[LoreFact]:
        query_words = set(query.lower().split())
        scored_facts = []

        for fact in self._facts.values():
            fact_words = set(fact.statement.lower().split()) | set(fact.entity_name.lower().split())
            score = len(query_words & fact_words)
            if score > 0:
                scored_facts.append((score, fact))

        scored_facts.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored_facts[:limit]]

    def commit_atomic_fact(self, fact: LoreFact) -> None:
        self._facts[fact.fact_id] = fact

    def save_draft_conversation(self, session_id: str, prompt: str, response: str) -> None:
        self._conversations.append({
            "session_id": session_id,
            "prompt": prompt,
            "response": response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def publish_wiki_page(self, entity: LoreEntityAggregate) -> str:
        page_id = f"wiki_{entity.name.lower().replace(' ', '_')}"
        backlinks = [rel.target_entity_name for rel in entity.relations]
        self._wiki_pages[page_id] = {
            "title": entity.name,
            "type": entity.entity_type.value,
            "summary": entity.summary,
            "description": entity.description,
            "backlinks": backlinks,
            "facts": [f.statement for f in entity.facts],
            "status": entity.status.value,
        }
        return f"/v3/wiki/page/{page_id}"

    def get_entity_wiki_graph(self, entity_name: str) -> Dict[str, Any]:
        target = entity_name.lower().replace(' ', '_')
        page_id = f"wiki_{target}"
        if page_id in self._wiki_pages:
            page = self._wiki_pages[page_id]
            return {
                "node": page["title"],
                "type": page["type"],
                "outbound_links": page["backlinks"],
                "inbound_links": [
                    p["title"] for p in self._wiki_pages.values() if page["title"] in p.get("backlinks", [])
                ],
            }
        return {"node": entity_name, "outbound_links": [], "inbound_links": []}
