import logging
from typing import List, Optional, Callable
from .models import Entity, Task, WorldBible
from .store import LoreStore
from .judge import LoreJudge
from .llm import LoreLLMClient

logger = logging.getLogger(__name__)


class AutonomousLoreEngine:
    """Core autonomous worldbuilding engine powered by the Red-Links queue growth algorithm and self-healing canon repair."""

    def __init__(
        self,
        store: LoreStore,
        llm: LoreLLMClient,
        judge: LoreJudge,
        world_bible: Optional[WorldBible] = None,
        max_entities: int = 10,
        max_depth: int = 3,
        on_entity_generated: Optional[Callable[[Entity, Task, List[Task]], None]] = None,
        on_repair_attempt: Optional[Callable[[Entity, List[str], int], None]] = None,
    ):
        self.store = store
        self.llm = llm
        self.judge = judge
        self.world_bible = world_bible or self.store.get_world()
        self.max_entities = max_entities
        self.max_depth = max_depth
        self.on_entity_generated = on_entity_generated
        self.on_repair_attempt = on_repair_attempt

        # Persist world bible
        self.store.save_world(self.world_bible)

    def seed(self, seed_tasks: List[Task]) -> int:
        """Seeds the initial tasks into the queue."""
        added = 0
        for task in seed_tasks:
            if self.store.push_task(task):
                added += 1
        return added

    def run(self) -> List[Entity]:
        """Runs the autonomous generation loop until queue is empty or budget (max_entities) is reached."""
        generated: List[Entity] = []

        while self.store.queue_size() > 0 and self.store.total_entities_count() < self.max_entities:
            task = self.store.pop_task()
            if not task:
                break

            # Avoid re-generating existing entities
            if self.store.exists_entity(task.name):
                continue

            # 1. Retrieve compact context
            context_facts = self.store.get_context_facts(task, limit=5)

            # 2. Generate entity
            try:
                entity = self.llm.generate_entity(task, context_facts, self.world_bible)
            except Exception as e:
                logger.error(f"Failed to generate entity for task '{task.name}': {e}")
                continue

            # 3. Self-healing reflection loop (up to 3 repair attempts)
            for attempt in range(1, 4):
                problems = self.judge.audit(entity, self.world_bible, context_facts)
                if not problems:
                    break

                if self.on_repair_attempt:
                    self.on_repair_attempt(entity, problems, attempt)

                try:
                    entity = self.llm.repair_entity(entity, problems, context_facts, self.world_bible)
                except Exception as e:
                    logger.warning(f"Repair attempt {attempt} failed for '{entity.name}': {e}")
                    break

            # 4. Commit to SQLite
            self.store.commit_entity(entity)
            generated.append(entity)

            # 5. Red-Links Expansion: Unknown targets become new tasks in the queue
            new_red_links = []
            if task.depth + 1 <= self.max_depth:
                for rel in entity.relations:
                    target_name = rel.target.strip()
                    if not target_name:
                        continue

                    # If target doesn't exist in store, queue it as a red-link task
                    if not self.store.exists_entity(target_name):
                        red_task = Task(
                            name=target_name,
                            hint=f"Связана с '{entity.name}': {rel.context} (отношение: {rel.type})",
                            source_entity=entity.name,
                            depth=task.depth + 1,
                            priority=max(1, 10 - (task.depth + 1)),
                        )
                        if self.store.push_task(red_task):
                            new_red_links.append(red_task)

            # 6. Notify callback
            if self.on_entity_generated:
                self.on_entity_generated(entity, task, new_red_links)

        return generated
