import os
import json
import sqlite3
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from .models import Entity, Relation, Task, WorldBible, EntityType


class LoreStore:
    """Persistent SQLite store for autonomous lore generation with queue and multi-tier memory."""

    def __init__(self, db_path: str = "output/lore_engine.db"):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.create_function("py_lower", 1, lambda s: s.lower() if s else "")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS world (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    cosmology TEXT,
                    laws TEXT,
                    tone TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    name TEXT PRIMARY KEY,
                    entity_type TEXT,
                    summary TEXT,
                    description TEXT,
                    era TEXT,
                    year INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_name TEXT,
                    statement TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT,
                    target_name TEXT,
                    rel_type TEXT,
                    context TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    name TEXT PRIMARY KEY,
                    entity_type TEXT,
                    hint TEXT,
                    source_entity TEXT,
                    depth INTEGER,
                    priority INTEGER,
                    status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    prompt TEXT,
                    response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_world(self, world: WorldBible) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO world (id, name, cosmology, laws, tone)
                VALUES ('current', ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    cosmology=excluded.cosmology,
                    laws=excluded.laws,
                    tone=excluded.tone
            """, (world.name, world.cosmology, json.dumps(world.immutable_laws, ensure_ascii=False), world.tone))
            conn.commit()

    def get_world(self) -> WorldBible:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM world WHERE id='current'").fetchone()
            if row:
                laws = json.loads(row["laws"]) if row["laws"] else []
                return WorldBible(
                    name=row["name"],
                    cosmology=row["cosmology"],
                    immutable_laws=laws,
                    tone=row["tone"],
                )
            return WorldBible()

    def exists_entity(self, name: str) -> bool:
        clean = name.strip().lower()
        with self._get_conn() as conn:
            row = conn.execute("SELECT 1 FROM entities WHERE py_lower(TRIM(name)) = ?", (clean,)).fetchone()
            return row is not None

    def commit_entity(self, entity: Entity) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO entities (name, entity_type, summary, description, era, year)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    entity_type=excluded.entity_type,
                    summary=excluded.summary,
                    description=excluded.description,
                    era=excluded.era,
                    year=excluded.year
            """, (entity.name, entity.entity_type.value, entity.summary, entity.description, entity.era, entity.year))

            # Commit facts
            for fact_text in entity.facts:
                # Avoid exact duplicates
                exists = cursor.execute(
                    "SELECT 1 FROM facts WHERE entity_name=? AND statement=?",
                    (entity.name, fact_text)
                ).fetchone()
                if not exists:
                    cursor.execute(
                        "INSERT INTO facts (entity_name, statement) VALUES (?, ?)",
                        (entity.name, fact_text)
                    )

            # Commit relations
            for rel in entity.relations:
                exists_rel = cursor.execute(
                    "SELECT 1 FROM relations WHERE source_name=? AND target_name=? AND rel_type=?",
                    (entity.name, rel.target, rel.type)
                ).fetchone()
                if not exists_rel:
                    cursor.execute(
                        "INSERT INTO relations (source_name, target_name, rel_type, context) VALUES (?, ?, ?, ?)",
                        (entity.name, rel.target, rel.type, rel.context)
                    )

            # Mark in queue as completed if it was queued
            cursor.execute("UPDATE queue SET status='completed' WHERE py_lower(TRIM(name)) = ?", (entity.name.lower().strip(),))
            conn.commit()

    def push_task(self, task: Task) -> bool:
        clean = task.name.strip().lower()
        if self.exists_entity(task.name):
            return False

        with self._get_conn() as conn:
            cursor = conn.cursor()
            existing = cursor.execute("SELECT 1 FROM queue WHERE py_lower(TRIM(name)) = ?", (clean,)).fetchone()
            if existing:
                return False

            type_val = task.entity_type.value if task.entity_type else None
            cursor.execute("""
                INSERT OR IGNORE INTO queue (name, entity_type, hint, source_entity, depth, priority, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """, (task.name, type_val, task.hint, task.source_entity, task.depth, task.priority))
            inserted = cursor.rowcount > 0
            conn.commit()
            return inserted

    def pop_task(self) -> Optional[Task]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            row = cursor.execute("""
                SELECT * FROM queue
                WHERE status = 'pending'
                ORDER BY priority DESC, depth ASC, rowid ASC
                LIMIT 1
            """).fetchone()

            if not row:
                return None

            cursor.execute("UPDATE queue SET status = 'in_progress' WHERE name = ?", (row["name"],))
            conn.commit()

            e_type = EntityType(row["entity_type"]) if row["entity_type"] else None
            return Task(
                name=row["name"],
                entity_type=e_type,
                hint=row["hint"] or "",
                source_entity=row["source_entity"],
                depth=row["depth"],
                priority=row["priority"],
                status="in_progress",
            )

    def queue_size(self) -> int:
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM queue WHERE status = 'pending'").fetchone()
            return row["cnt"] if row else 0

    def total_entities_count(self) -> int:
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM entities").fetchone()
            return row["cnt"] if row else 0

    def get_compressed_world_context(self, task: Task, recent_window: int = 3) -> str:
        """Hybrid memory retrieval with graph compression: compact 1-line summaries for older entities,
        detailed facts for immediately connected and recent entities.
        Keeps LLM token budget constant even for hundreds of entities in graph.
        """
        with self._get_conn() as conn:
            parts = []

            # 1. Compact compressed summary of older entities (Graph compression / pruning)
            older = conn.execute(
                "SELECT name, entity_type, summary, year FROM entities ORDER BY rowid ASC"
            ).fetchall()
            if len(older) > recent_window:
                older_summaries = [
                    f"• [{r['entity_type'].upper()}] {r['name']} ({r['year']} г.): {r['summary'][:100]}..."
                    for r in older[:-recent_window]
                ]
                parts.append("СЖАТАЯ ХРОНИКА МИРА (АРХИВ ГРАФА):\n" + "\n".join(older_summaries[-5:]))

            # 2. Direct facts from source entity (immediate parent context)
            if task.source_entity:
                source_facts = conn.execute(
                    "SELECT statement FROM facts WHERE entity_name = ? LIMIT 3",
                    (task.source_entity,)
                ).fetchall()
                if source_facts:
                    parts.append(
                        f"ФАКТЫ СВЯЗАННОЙ СУЩНОСТИ '{task.source_entity}':\n"
                        + "\n".join(f"- {r['statement']}" for r in source_facts)
                    )

            # 3. Most recent verified facts
            recent_facts = conn.execute(
                "SELECT entity_name, statement FROM facts ORDER BY id DESC LIMIT ?",
                (recent_window * 2,)
            ).fetchall()
            if recent_facts:
                recent_lines = [f"- [{r['entity_name']}] {r['statement']}" for r in recent_facts]
                parts.append("ПОСЛЕДНИЕ СОБЫТИЯ В МИРЕ:\n" + "\n".join(recent_lines[:4]))

            return "\n\n".join(parts) if parts else "Нет зафиксированных фактов."

    def get_context_facts(self, task: Task, limit: int = 5) -> str:
        """Retrieves top-k relevant facts from SQLite to feed into LLM prompt."""
        return self.get_compressed_world_context(task, recent_window=3)

    def record_conversation(self, session_id: str, prompt: str, response: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO conversations (session_id, prompt, response) VALUES (?, ?, ?)",
                (session_id, prompt, response)
            )
            conn.commit()

    def export_memory_json(self, file_path: str) -> str:
        """Exports the SQLite store to the standard multi-tier L0-L3 memory JSON format."""
        world = self.get_world()
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with self._get_conn() as conn:
            # L1 Atomic facts
            fact_rows = conn.execute("SELECT * FROM facts ORDER BY id ASC").fetchall()
            l1_facts = [
                {
                    "fact_id": f"f_{r['id']:04d}",
                    "entity_name": r["entity_name"],
                    "statement": r["statement"],
                    "created_at": r["created_at"],
                }
                for r in fact_rows
            ]

            # L0 Conversations
            conv_rows = conn.execute("SELECT * FROM conversations ORDER BY id ASC").fetchall()
            l0_convs = [
                {
                    "session_id": r["session_id"],
                    "prompt": r["prompt"],
                    "response": r["response"],
                    "timestamp": r["created_at"],
                }
                for r in conv_rows
            ]

            # Wiki knowledge graph
            entities_rows = conn.execute("SELECT * FROM entities").fetchall()
            wiki_graph = {}
            for e in entities_rows:
                name = e["name"]
                key = f"wiki_{name.lower().replace(' ', '_')}"
                rel_rows = conn.execute("SELECT target_name FROM relations WHERE source_name = ?", (name,)).fetchall()
                backlinks = [r["target_name"] for r in rel_rows]
                e_facts = conn.execute("SELECT statement FROM facts WHERE entity_name = ?", (name,)).fetchall()

                wiki_graph[key] = {
                    "title": name,
                    "type": e["entity_type"],
                    "summary": e["summary"],
                    "description": e["description"],
                    "era": e["era"],
                    "year": e["year"],
                    "backlinks": backlinks,
                    "facts": [f["statement"] for f in e_facts],
                    "status": "canonical",
                }

        payload = {
            "l3_core": {
                "world_id": "sqlite_lore_engine",
                "name": world.name,
                "cosmology": world.cosmology,
                "immutable_laws": world.immutable_laws,
                "tone": world.tone,
            },
            "l1_atomic_facts": l1_facts,
            "l0_conversations": l0_convs,
            "knowledge_wiki_graph": wiki_graph,
        }

        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        return abs_path

    def export_results_json(self, file_path: str) -> str:
        """Exports the generated entities and relationships into workflow results JSON format."""
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        results = []
        with self._get_conn() as conn:
            entities = conn.execute("SELECT * FROM entities ORDER BY rowid ASC").fetchall()
            for idx, e in enumerate(entities, 1):
                name = e["name"]
                facts = [r["statement"] for r in conn.execute("SELECT statement FROM facts WHERE entity_name=?", (name,))]
                rels = [
                    {"target": r["target_name"], "type": r["rel_type"], "context": r["context"]}
                    for r in conn.execute("SELECT target_name, rel_type, context FROM relations WHERE source_name=?", (name,))
                ]
                results.append({
                    "task_index": idx,
                    "task_type": "generate",
                    "status": "SUCCESS",
                    "result": {
                        "entity_name": name,
                        "entity_type": e["entity_type"],
                        "status": "canonical",
                        "summary": e["summary"],
                        "description": e["description"],
                        "timeline": f"{e['year']} год ({e['era']})",
                        "facts": facts,
                        "relations": rels,
                    }
                })

        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return abs_path
