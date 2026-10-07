from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from ....domain.model.aggregate import WorldBibleAggregate, LoreEntityAggregate
from ....domain.model.entity import LoreFact


class MemoryPort(ABC):
    """Outbound SPI port for interacting with hierarchical memory (L0-L3 + Wiki)."""

    @abstractmethod
    def get_world_bible(self) -> WorldBibleAggregate:
        """Fetch L3 Core: World Bible axioms, cosmology and rules."""
        pass

    @abstractmethod
    def save_world_bible(self, bible: WorldBibleAggregate) -> None:
        """Persist L3 Core: World Bible."""
        pass

    @abstractmethod
    def search_canonical_facts(self, query: str, limit: int = 5) -> List[LoreFact]:
        """Search L1 Atomic Facts using semantic vector/BM25 retrieval."""
        pass

    @abstractmethod
    def commit_atomic_fact(self, fact: LoreFact) -> None:
        """Persist verified fact into L1 Atomic memory."""
        pass

    @abstractmethod
    def save_draft_conversation(self, session_id: str, prompt: str, response: str) -> None:
        """Record raw LLM generation exchange into L0 conversation memory."""
        pass

    @abstractmethod
    def publish_wiki_page(self, entity: LoreEntityAggregate) -> str:
        """Publish entity to MemoryKnowledge Wiki with backlinks and graph metadata."""
        pass

    @abstractmethod
    def get_entity_wiki_graph(self, entity_name: str) -> Dict[str, Any]:
        """Query wiki link graph for relationships and connected entity nodes."""
        pass

    @abstractmethod
    def export_memory_snapshot(self) -> Dict[str, Any]:
        """Export complete state of all memory tiers (L3 Core, L1 Facts, L0 Conversations, Knowledge Wiki)."""
        pass

    @abstractmethod
    def dump_to_json(self, file_path: str) -> str:
        """Persist full hierarchical memory snapshot (L0-L3) into a JSON file."""
        pass
