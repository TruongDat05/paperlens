"""Manage SQLite database schema, connections, and transactions.

Provide SQLite initialization, connection management with WAL mode,
and atomic transaction contexts for owner-scoped data and accounting.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
import json
import sqlite3
import threading

from backend.app.core.config import get_settings

_local = threading.local()


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a thread-local SQLite connection with WAL mode and foreign keys enabled."""
    target_path = db_path or get_settings().db_path
    if not hasattr(_local, "connections"):
        _local.connections = {}

    if target_path not in _local.connections:
        conn = sqlite3.connect(target_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _local.connections[target_path] = conn
        init_db(target_path)
    return _local.connections[target_path]


@contextmanager
def transaction(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Execute a block within an atomic SQLite transaction."""
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Safely migrate passages and vectors tables to compound primary keys (paper_id, passage_id).

    Preserves all existing rows without deleting the database.
    """
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='passages'")
    if cursor.fetchone():
        cols = conn.execute("PRAGMA table_info(passages)").fetchall()
        pk_cols = {c["name"] for c in cols if c["pk"] > 0}
        has_fingerprint = any(c["name"] == "fingerprint" for c in cols)
        if pk_cols != {"paper_id", "passage_id"}:
            conn.execute("PRAGMA foreign_keys=OFF;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS passages_migrated (
                    passage_id TEXT NOT NULL,
                    parent_passage_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    section_path TEXT NOT NULL,
                    paragraph_order INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source_locator TEXT NOT NULL,
                    offset_start INTEGER DEFAULT 0,
                    offset_end INTEGER DEFAULT 0,
                    fingerprint TEXT,
                    PRIMARY KEY (paper_id, passage_id),
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
                );
            """)
            if has_fingerprint:
                conn.execute("""
                    INSERT OR IGNORE INTO passages_migrated (
                        passage_id, parent_passage_id, paper_id, section_id,
                        section_path, paragraph_order, text, source_locator,
                        offset_start, offset_end, fingerprint
                    )
                    SELECT passage_id, parent_passage_id, paper_id, section_id,
                           section_path, paragraph_order, text, source_locator,
                           offset_start, offset_end, fingerprint
                    FROM passages;
                """)
            else:
                conn.execute("""
                    INSERT OR IGNORE INTO passages_migrated (
                        passage_id, parent_passage_id, paper_id, section_id,
                        section_path, paragraph_order, text, source_locator,
                        offset_start, offset_end
                    )
                    SELECT passage_id, parent_passage_id, paper_id, section_id,
                           section_path, paragraph_order, text, source_locator,
                           offset_start, offset_end
                    FROM passages;
                """)
            conn.execute("DROP TABLE passages;")
            conn.execute("ALTER TABLE passages_migrated RENAME TO passages;")
            conn.execute("PRAGMA foreign_keys=ON;")
        elif not has_fingerprint:
            conn.execute("ALTER TABLE passages ADD COLUMN fingerprint TEXT;")

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vectors'")
    if cursor.fetchone():
        cols = conn.execute("PRAGMA table_info(vectors)").fetchall()
        pk_cols = {c["name"] for c in cols if c["pk"] > 0}
        if pk_cols != {"paper_id", "passage_id"}:
            conn.execute("PRAGMA foreign_keys=OFF;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vectors_migrated (
                    passage_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (paper_id, passage_id),
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                INSERT OR IGNORE INTO vectors_migrated (
                    passage_id, paper_id, owner_id, model_id, embedding, created_at
                )
                SELECT passage_id, paper_id, owner_id, model_id, embedding, created_at
                FROM vectors;
            """)
            conn.execute("DROP TABLE vectors;")
            conn.execute("ALTER TABLE vectors_migrated RENAME TO vectors;")
            conn.execute("PRAGMA foreign_keys=ON;")

    # 3. Check runs table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
    if cursor.fetchone():
        cols = conn.execute("PRAGMA table_info(runs)").fetchall()
        if not any(c["name"] == "retrieval_fallback_reason" for c in cols):
            conn.execute("ALTER TABLE runs ADD COLUMN retrieval_fallback_reason TEXT;")
        has_limitations = any(c["name"] == "limitations" for c in cols)
        if not has_limitations:
            conn.execute("ALTER TABLE runs ADD COLUMN limitations TEXT;")
        for name, definition in (("question", "TEXT"), ("images", "TEXT"), ("chat_id", "TEXT"), ("follow_ups", "TEXT"), ("tokens_used", "INTEGER DEFAULT 0")):
            if not any(c["name"] == name for c in cols):
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {definition}")


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize SQLite tables for papers, passages, vectors, runs, and quotas."""
    target_path = db_path or get_settings().db_path
    if target_path != ":memory:":
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(target_path)
    with conn:
        _migrate_schema(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, owner_id TEXT NOT NULL);

            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                arxiv_id TEXT NOT NULL,
                version TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                title TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                lexical_ready INTEGER DEFAULT 0,
                semantic_ready INTEGER DEFAULT 0,
                indexing_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (owner_id, arxiv_id, version, content_hash)
            );

            CREATE TABLE IF NOT EXISTS sections (
                section_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                heading TEXT NOT NULL,
                path TEXT NOT NULL,
                section_order INTEGER NOT NULL,
                section_type TEXT,
                PRIMARY KEY (paper_id, section_id),
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS passages (
                passage_id TEXT NOT NULL,
                parent_passage_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                section_id TEXT NOT NULL,
                section_path TEXT NOT NULL,
                paragraph_order INTEGER NOT NULL,
                text TEXT NOT NULL,
                source_locator TEXT NOT NULL,
                offset_start INTEGER DEFAULT 0,
                offset_end INTEGER DEFAULT 0,
                fingerprint TEXT,
                PRIMARY KEY (paper_id, passage_id),
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS vectors (
                passage_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (paper_id, passage_id),
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                retrieval_mode TEXT,
                retrieval_fallback_reason TEXT,
                serving_model TEXT,
                fallback_reason TEXT,
                answer_blocks TEXT,
                evidence_ids TEXT,
                step_progress TEXT,
                error_message TEXT,
                limitations TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deadline TEXT NOT NULL,
                chat_id TEXT,
                question TEXT,
                images TEXT,
                follow_ups TEXT,
                tokens_used INTEGER DEFAULT 0,
                UNIQUE (owner_id, request_id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                chat_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                usage_estimated INTEGER NOT NULL DEFAULT 0,
                exhausted INTEGER NOT NULL DEFAULT 0,
                token_limit INTEGER NOT NULL DEFAULT 500000,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS quotas (
                owner_id TEXT NOT NULL,
                date TEXT NOT NULL,
                new_indexes INTEGER DEFAULT 0,
                agent_turns INTEGER DEFAULT 0,
                semantic_retrievals INTEGER DEFAULT 0,
                PRIMARY KEY (owner_id, date)
            );

            CREATE TABLE IF NOT EXISTS usage_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                run_id TEXT,
                operation TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_papers_owner ON papers (owner_id);
            CREATE INDEX IF NOT EXISTS idx_passages_paper ON passages (paper_id);
            CREATE INDEX IF NOT EXISTS idx_vectors_paper ON vectors (paper_id);
            CREATE INDEX IF NOT EXISTS idx_runs_owner ON runs (owner_id);
            CREATE INDEX IF NOT EXISTS idx_runs_paper ON runs (paper_id);
            CREATE INDEX IF NOT EXISTS idx_runs_chat ON runs (chat_id, created_at);
            CREATE TABLE IF NOT EXISTS profiles (
                owner_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                research_area TEXT NOT NULL DEFAULT '',
                nationality TEXT NOT NULL DEFAULT '',
                memory_enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS identities (
                provider TEXT NOT NULL,
                subject TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                PRIMARY KEY (provider, subject)
            );
            CREATE TABLE IF NOT EXISTS oauth_states (
                state_hash TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                session_hash TEXT NOT NULL,
                provider TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                verifier TEXT NOT NULL,
                expires_at REAL NOT NULL,
                ticket_hash TEXT UNIQUE,
                identity_json TEXT
            );
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                paper_id TEXT,
                source_run_id TEXT,
                source_label TEXT NOT NULL DEFAULT '',
                source_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE,
                FOREIGN KEY (source_run_id) REFERENCES runs(run_id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_owner ON memories (owner_id, updated_at);
        """)
        # Raise existing chats' allowance without deleting usage or conversation data.
        from backend.app.core.config import CHAT_TOKEN_LIMIT
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversations)")}
        if "token_limit" not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN token_limit INTEGER NOT NULL DEFAULT 50000")
        conn.execute("UPDATE conversations SET token_limit = ?, exhausted = 0 WHERE token_limit < ?", (CHAT_TOKEN_LIMIT, CHAT_TOKEN_LIMIT))
