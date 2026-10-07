from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List


@dataclass
class LoreFact:
    """Atomic fact representing a verified canonical truth (mapped to L1 memory)."""
    fact_id: str
    entity_name: str
    statement: str
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_wiki_entry(self) -> str:
        return f"- **{self.statement}** (tags: {', '.join(self.tags)})"
