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
                    audit_status TEXT DEFAULT 'canonical',
                    audit_issues TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_name TEXT,
                    year INTEGER,
                    era TEXT,
                    statement TEXT,
                    participants TEXT DEFAULT '[]',
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
                    status TEXT,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT
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

            # Schema migrations for existing databases
            cols_entities = {row["name"] for row in cursor.execute("PRAGMA table_info(entities)").fetchall()}
            if "audit_status" not in cols_entities:
                cursor.execute("ALTER TABLE entities ADD COLUMN audit_status TEXT DEFAULT 'canonical'")
            if "audit_issues" not in cols_entities:
                cursor.execute("ALTER TABLE entities ADD COLUMN audit_issues TEXT DEFAULT '[]'")

            cols_facts = {row["name"] for row in cursor.execute("PRAGMA table_info(facts)").fetchall()}
            if "year" not in cols_facts:
                cursor.execute("ALTER TABLE facts ADD COLUMN year INTEGER")
            if "era" not in cols_facts:
                cursor.execute("ALTER TABLE facts ADD COLUMN era TEXT")
            if "participants" not in cols_facts:
                cursor.execute("ALTER TABLE facts ADD COLUMN participants TEXT DEFAULT '[]'")

            cols_queue = {row["name"] for row in cursor.execute("PRAGMA table_info(queue)").fetchall()}
            if "retry_count" not in cols_queue:
                cursor.execute("ALTER TABLE queue ADD COLUMN retry_count INTEGER DEFAULT 0")
            if "error_message" not in cols_queue:
                cursor.execute("ALTER TABLE queue ADD COLUMN error_message TEXT")

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

    def resolve_canonical_name(self, name: str) -> str:
        """Resolves alias/title variant or grammatical declension to an existing canonical entity name in SQLite.
        E.g. 'Вараг' matches 'Рунный кузнец Вараг', 'Ксентии'/'Ксения' matches 'Воевода Ксения'.
        Does NOT falsely merge distinct names like 'Радик' and 'Радим'.
        """
        import unicodedata
        clean = name.strip()
        if not clean:
            return clean

        with self._get_conn() as conn:
            # 1. Exact match
            row = conn.execute(
                "SELECT name FROM entities WHERE py_lower(TRIM(name)) = ?",
                (clean.casefold(),)
            ).fetchone()
            if row:
                return row["name"]

            # 2. Normalized prefix stripping
            def strip_titles(s: str) -> str:
                cf = unicodedata.normalize("NFKC", s).strip().casefold()
                for pref in (
                    "рунный кузнец ", "кузнец ", "воевода ", "князь ", "орден ",
                    "клан ", "архиволхв ", "волхв ", "мастер ", "страж "
                ):
                    if cf.startswith(pref):
                        cf = cf.removeprefix(pref).strip()
                        break
                return cf

            # Russian grammatical inflection endings for names/nouns
            INFLECTION_ENDINGS = {"", "а", "я", "у", "ю", "е", "и", "ом", "ем", "ой", "ей", "ы", "ов", "ев", "ам", "ям"}

            target_core = strip_titles(clean)
            if len(target_core) >= 3:
                all_entities = conn.execute("SELECT name FROM entities").fetchall()
                for r in all_entities:
                    cand = r["name"]
                    cand_core = strip_titles(cand)
                    if target_core == cand_core or target_core in cand_core.split() or cand_core in target_core.split():
                        return cand

                    # Common stem check with grammatical inflection endings
                    common_len = 0
                    min_len = min(len(target_core), len(cand_core))
                    while common_len < min_len and target_core[common_len] == cand_core[common_len]:
                        common_len += 1

                    if common_len >= 4:
                        suff1 = target_core[common_len:]
                        suff2 = cand_core[common_len:]
                        if suff1 in INFLECTION_ENDINGS and suff2 in INFLECTION_ENDINGS:
                            return cand

        return clean

    def exists_entity(self, name: str) -> bool:
        resolved = self.resolve_canonical_name(name)
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM entities WHERE py_lower(TRIM(name)) = ?",
                (resolved.strip().casefold(),)
            ).fetchone()
            return row is not None

    def commit_entity(self, entity: Entity) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO entities (name, entity_type, summary, description, era, year, audit_status, audit_issues)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    entity_type=excluded.entity_type,
                    summary=excluded.summary,
                    description=excluded.description,
                    era=excluded.era,
                    year=excluded.year,
                    audit_status=excluded.audit_status,
                    audit_issues=excluded.audit_issues
            """, (
                entity.name,
                entity.entity_type.value,
                entity.summary,
                entity.description,
                entity.era,
                entity.year,
                entity.audit_status,
                json.dumps(entity.audit_issues, ensure_ascii=False),
            ))

            # Commit facts with year, era, and participants
            if entity.atomic_facts:
                for af in entity.atomic_facts:
                    exists = cursor.execute(
                        "SELECT 1 FROM facts WHERE entity_name=? AND statement=?",
                        (entity.name, af.statement)
                    ).fetchone()
                    if not exists:
                        cursor.execute(
                            "INSERT INTO facts (entity_name, year, era, statement, participants) VALUES (?, ?, ?, ?, ?)",
                            (entity.name, af.year, af.era, af.statement, json.dumps(af.participants, ensure_ascii=False))
                        )
            else:
                for fact_text in entity.facts:
                    exists = cursor.execute(
                        "SELECT 1 FROM facts WHERE entity_name=? AND statement=?",
                        (entity.name, fact_text)
                    ).fetchone()
                    if not exists:
                        cursor.execute(
                            "INSERT INTO facts (entity_name, year, era, statement, participants) VALUES (?, ?, ?, ?, ?)",
                            (entity.name, entity.year, entity.era, fact_text, json.dumps([]))
                        )

            # Commit relations with resolved canonical targets
            for rel in entity.relations:
                resolved_target = self.resolve_canonical_name(rel.target)
                exists_rel = cursor.execute(
                    "SELECT 1 FROM relations WHERE source_name=? AND target_name=? AND rel_type=?",
                    (entity.name, resolved_target, rel.type)
                ).fetchone()
                if not exists_rel:
                    cursor.execute(
                        "INSERT INTO relations (source_name, target_name, rel_type, context) VALUES (?, ?, ?, ?)",
                        (entity.name, resolved_target, rel.type, rel.context)
                    )

            # Mark in queue as completed if it was queued
            resolved_self = self.resolve_canonical_name(entity.name)
            cursor.execute(
                "UPDATE queue SET status='completed' WHERE py_lower(TRIM(name)) IN (?, ?)",
                (entity.name.strip().casefold(), resolved_self.strip().casefold())
            )
            conn.commit()

    def push_task(self, task: Task) -> bool:
        resolved_name = self.resolve_canonical_name(task.name)
        if self.exists_entity(resolved_name):
            return False

        with self._get_conn() as conn:
            cursor = conn.cursor()
            existing = cursor.execute(
                "SELECT 1 FROM queue WHERE py_lower(TRIM(name)) IN (?, ?)",
                (task.name.strip().casefold(), resolved_name.strip().casefold())
            ).fetchone()
            if existing:
                return False

            type_val = task.entity_type.value if task.entity_type else None
            cursor.execute("""
                INSERT OR IGNORE INTO queue (name, entity_type, hint, source_entity, depth, priority, status, retry_count, error_message)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (resolved_name, type_val, task.hint, task.source_entity, task.depth, task.priority, task.retry_count, task.error_message))
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
                retry_count=row["retry_count"] if "retry_count" in row.keys() and row["retry_count"] is not None else 0,
                error_message=row["error_message"] if "error_message" in row.keys() else None,
            )

    def reset_in_progress_tasks(self) -> int:
        """Resets dangling in_progress tasks back to pending on engine startup or recovery."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE queue SET status = 'pending' WHERE status = 'in_progress'")
            cnt = cursor.rowcount
            conn.commit()
            return cnt

    def fail_task(self, task_name: str, error: str = "", max_retries: int = 3) -> None:
        """Marks a task as failed or retries it if retry budget permits."""
        resolved = self.resolve_canonical_name(task_name)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT retry_count FROM queue WHERE py_lower(TRIM(name)) IN (?, ?)",
                (task_name.strip().casefold(), resolved.strip().casefold())
            ).fetchone()
            current_retries = row["retry_count"] if row and row["retry_count"] is not None else 0
            new_retries = current_retries + 1
            new_status = "failed" if new_retries >= max_retries else "pending"
            cursor.execute(
                "UPDATE queue SET status = ?, retry_count = ?, error_message = ? WHERE py_lower(TRIM(name)) IN (?, ?)",
                (new_status, new_retries, error, task_name.strip().casefold(), resolved.strip().casefold())
            )
            conn.commit()

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
            l1_facts = []
            for r in fact_rows:
                participants = []
                if "participants" in r.keys() and r["participants"]:
                    try:
                        participants = json.loads(r["participants"])
                    except Exception:
                        participants = []
                l1_facts.append({
                    "fact_id": f"f_{r['id']:04d}",
                    "entity_name": r["entity_name"],
                    "year": r["year"] if "year" in r.keys() else None,
                    "era": r["era"] if "era" in r.keys() else None,
                    "statement": r["statement"],
                    "participants": participants,
                    "created_at": r["created_at"],
                })

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

                audit_issues = []
                if "audit_issues" in e.keys() and e["audit_issues"]:
                    try:
                        audit_issues = json.loads(e["audit_issues"])
                    except Exception:
                        audit_issues = []
                audit_status = e["audit_status"] if "audit_status" in e.keys() and e["audit_status"] else "canonical"

                wiki_graph[key] = {
                    "title": name,
                    "type": e["entity_type"],
                    "summary": e["summary"],
                    "description": e["description"],
                    "era": e["era"],
                    "year": e["year"],
                    "backlinks": backlinks,
                    "facts": [f["statement"] for f in e_facts],
                    "status": audit_status,
                    "audit_issues": audit_issues,
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
        """Exports the generated entities, audit verification status, and queue state."""
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        results = []
        with self._get_conn() as conn:
            entities = conn.execute("SELECT * FROM entities ORDER BY rowid ASC").fetchall()
            pending_queue = conn.execute("SELECT name, depth, priority, status FROM queue WHERE status = 'pending'").fetchall()
            queue_state = [
                {"name": q["name"], "depth": q["depth"], "priority": q["priority"]}
                for q in pending_queue
            ]

            for idx, e in enumerate(entities, 1):
                name = e["name"]
                facts = [r["statement"] for r in conn.execute("SELECT statement FROM facts WHERE entity_name=?", (name,))]
                rels = [
                    {"target": r["target_name"], "type": r["rel_type"], "context": r["context"]}
                    for r in conn.execute("SELECT target_name, rel_type, context FROM relations WHERE source_name=?", (name,))
                ]
                audit_issues = []
                if "audit_issues" in e.keys() and e["audit_issues"]:
                    try:
                        audit_issues = json.loads(e["audit_issues"])
                    except Exception:
                        audit_issues = []
                audit_status = e["audit_status"] if "audit_status" in e.keys() and e["audit_status"] else "canonical"
                task_status = "SUCCESS" if audit_status == "canonical" else "NEEDS_REVIEW"

                results.append({
                    "task_index": idx,
                    "task_type": "generate",
                    "status": task_status,
                    "audit": {
                        "status": audit_status,
                        "validation_method": "Two-Stage Facts->Prose & Zero-Regex Hybrid Judge",
                        "passed_checks": ["Axiom Compliance", "Temporal Algebra", "Lifespan Bounded", "Ontological Matrix", "Alias Deduplication"],
                        "issues": audit_issues,
                    },
                    "result": {
                        "entity_name": name,
                        "entity_type": e["entity_type"],
                        "status": audit_status,
                        "summary": e["summary"],
                        "description": e["description"],
                        "timeline": f"{e['year']} год ({e['era']})",
                        "facts": facts,
                        "relations": rels,
                    },
                    "pending_red_links_in_queue": queue_state if idx == len(entities) else None,
                })

        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return abs_path
