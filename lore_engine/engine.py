import logging
from typing import List, Optional, Callable, Any
from .models import Entity, Task, WorldBible, EntityFactsDraft
from .store import LoreStore
from .judge import LoreJudge
from .llm import LoreLLMClient

logger = logging.getLogger(__name__)


class AutonomousLoreEngine:
    """Core autonomous worldbuilding engine powered by Two-Stage (Facts -> Prose) generation,
    Red-Links queue growth algorithm, and zero-regex hybrid canon verification.
    """

    def __init__(
        self,
        store: LoreStore,
        llm: LoreLLMClient,
        judge: LoreJudge,
        world_bible: Optional[WorldBible] = None,
        max_entities: int = 10,
        max_depth: int = 3,
        on_entity_generated: Optional[Callable[[Entity, Task, List[Task]], None]] = None,
        on_repair_attempt: Optional[Callable[[Any, List[str], int], None]] = None,
    ):
        self.store = store
        self.llm = llm
        self.judge = judge
        self.world_bible = world_bible or self.store.get_world()
        self.max_entities = max_entities
        self.max_depth = max_depth
        self.on_entity_generated = on_entity_generated
        self.on_repair_attempt = on_repair_attempt

        # Persist world bible and reset any dangling in_progress tasks from previous runs
        self.store.save_world(self.world_bible)
        reset_count = self.store.reset_in_progress_tasks()
        if reset_count > 0:
            logger.info(f"Reset {reset_count} dangling in_progress tasks back to pending on startup.")

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

            # Avoid re-generating existing entities (with alias resolution)
            resolved_task_name = self.store.resolve_canonical_name(task.name)
            if self.store.exists_entity(resolved_task_name):
                # Mark redundant task as completed
                with self.store._get_conn() as conn:
                    conn.execute("UPDATE queue SET status = 'completed' WHERE name = ?", (task.name,))
                    conn.commit()
                continue

            # 1. Retrieve compact compressed context
            context_facts = self.store.get_context_facts(task, limit=5)

            # 2. STAGE 1: Generate atomic facts and relations draft (Facts-first)
            try:
                draft: EntityFactsDraft = self.llm.generate_facts_draft(task, context_facts, self.world_bible)
            except Exception as e:
                logger.error(f"Failed to generate facts draft for task '{task.name}': {e}")
                self.store.fail_task(task.name, f"Draft generation failed: {e}")
                continue

            # 3. STAGE 2: Self-healing audit and repair on facts draft
            draft_problems = []
            for attempt in range(1, 4):
                draft_problems = self.judge.audit_draft(draft, self.world_bible, context_facts)
                if not draft_problems:
                    break

                if self.on_repair_attempt:
                    self.on_repair_attempt(draft, draft_problems, attempt)

                try:
                    draft = self.llm.repair_facts_draft(draft, draft_problems, context_facts, self.world_bible)
                except Exception as e:
                    logger.warning(f"Repair draft attempt {attempt} failed for '{draft.name}': {e}")
                    break

            final_problems = self.judge.audit_draft(draft, self.world_bible, context_facts)

            # 4. STAGE 3: Synthesize summary and prose STRICTLY from accepted facts
            try:
                entity = self.llm.synthesize_prose(task, draft, self.world_bible)
            except Exception as e:
                logger.error(f"Prose synthesis failed for '{task.name}': {e}")
                self.store.fail_task(task.name, f"Prose synthesis failed: {e}")
                continue

            entity.atomic_facts = draft.facts
            if final_problems:
                entity.audit_status = "needs_review"
                entity.audit_issues = final_problems
                logger.warning(f"Entity '{entity.name}' has unresolved audit issues: {final_problems}")
            else:
                entity.audit_status = "canonical"
                entity.audit_issues = []

            entity.audit_notes = final_problems

            # 5. Commit to SQLite & Record L0 raw conversation
            self.store.commit_entity(entity)
            self.store.record_conversation(
                session_id=f"session_{entity.name.lower().replace(' ', '_')}",
                prompt=f"Task: {task.name} | Context: {context_facts[:200]}...",
                response=entity.model_dump_json(indent=2),
            )
            generated.append(entity)

            # 6. Red-Links Expansion: Unknown targets become new tasks in the queue
            new_red_links = []
            if task.depth + 1 <= self.max_depth:
                for rel in entity.relations:
                    target_name = rel.target.strip()
                    if not target_name:
                        continue

                    # Canonical alias resolution (e.g. 'Вараг' -> 'Рунный кузнец Вараг')
                    resolved_target = self.store.resolve_canonical_name(target_name)

                    # If target doesn't exist in store, queue it as a red-link task
                    if not self.store.exists_entity(resolved_target):
                        red_task = Task(
                            name=resolved_target,
                            hint=f"Связана с '{entity.name}': {rel.context} (отношение: {rel.type})",
                            source_entity=entity.name,
                            depth=task.depth + 1,
                            priority=max(1, 10 - (task.depth + 1)),
                        )
                        if self.store.push_task(red_task):
                            new_red_links.append(red_task)

            # 7. Notify callback
            if self.on_entity_generated:
                self.on_entity_generated(entity, task, new_red_links)

        return generated
