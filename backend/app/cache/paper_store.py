"""Store papers, passages, indexes, and ingest progress by owner.

Provide consistent paper-version data for retrieval and agent runs. Key
vector caches by owner, content hash, parser and chunking versions, and
embedding configuration, including model, snapshot, and prefix.

Record access times and remove expired papers and indexes according to
configuration. Coordinate deletion of derived data when the owner
requests it.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import json
import sqlite3

from backend.app.core.db import get_connection, transaction
from backend.app.core.schemas import (
    PaperIngestRequest,
    PassageChunk,
    SourceLocation,
    PaperStatusResponse,
)
from backend.app.retrieval.bm25 import BM25Index

# In-memory runtime caches for fast access during server process lifespan, keyed by (owner_id, paper_id)
_bm25_cache: Dict[Tuple[str, str], BM25Index] = {}
_chunks_cache: Dict[Tuple[str, str], List[PassageChunk]] = {}
_vectors_cache: Dict[Tuple[str, str], Dict[str, List[float]]] = {}


def get_current_timestamp() -> str:
    """Return ISO format UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def find_existing_paper(
    owner_id: str,
    arxiv_id: str,
    version: str,
    content_hash: str,
    db_path: Optional[str] = None,
) -> Optional[str]:
    """Find paper_id if identical content already indexed for owner."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        """
        SELECT paper_id FROM papers
        WHERE owner_id = ? AND arxiv_id = ? AND version = ? AND content_hash = ?
        """,
        (owner_id, arxiv_id, version, content_hash),
    )
    row = cursor.fetchone()
    return row["paper_id"] if row else None


def store_paper_and_chunks(
    paper_id: str,
    owner_id: str,
    paper_req: PaperIngestRequest,
    content_hash: str,
    chunks: List[PassageChunk],
    lexical_ready: bool = True,
    semantic_ready: bool = False,
    db_path: Optional[str] = None,
) -> None:
    """Persist paper metadata, sections, and passage chunks in SQLite."""
    now = get_current_timestamp()
    with transaction(db_path) as conn:
        # Insert paper record
        conn.execute(
            """
            INSERT OR REPLACE INTO papers (
                paper_id, owner_id, arxiv_id, version, canonical_url,
                title, content_hash, parser_version, lexical_ready,
                semantic_ready, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                owner_id,
                paper_req.arxiv_id,
                paper_req.version,
                paper_req.canonical_url,
                paper_req.title,
                content_hash,
                paper_req.parser_version,
                1 if lexical_ready else 0,
                1 if semantic_ready else 0,
                now,
                now,
            ),
        )

        # Insert sections
        for sec in paper_req.sections:
            conn.execute(
                """
                INSERT OR REPLACE INTO sections (
                    section_id, paper_id, heading, path, section_order, section_type
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sec.id, paper_id, sec.heading, sec.path, sec.order, sec.section_type),
            )

        # Insert passage chunks
        for chunk in chunks:
            conn.execute(
                """
                INSERT OR REPLACE INTO passages (
                    passage_id, parent_passage_id, paper_id, section_id,
                    section_path, paragraph_order, text, source_locator,
                    offset_start, offset_end, fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.passage_id,
                    chunk.parent_passage_id,
                    paper_id,
                    chunk.section_id,
                    chunk.section_path,
                    chunk.paragraph_order,
                    chunk.text,
                    chunk.locator.model_dump_json(),
                    chunk.offset_start,
                    chunk.offset_end,
                    chunk.fingerprint,
                ),
            )

    # Cache in memory keyed by (owner_id, paper_id)
    cache_key = (owner_id, paper_id)
    _chunks_cache[cache_key] = chunks
    if lexical_ready:
        _bm25_cache[cache_key] = BM25Index(chunks)


def get_paper_status(
    paper_id: str,
    owner_id: str,
    db_path: Optional[str] = None,
) -> Optional[PaperStatusResponse]:
    """Retrieve owner-scoped paper status."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        """
        SELECT paper_id, title, arxiv_id, version, lexical_ready,
               semantic_ready, indexing_error
        FROM papers
        WHERE paper_id = ? AND owner_id = ?
        """,
        (paper_id, owner_id),
    )
    row = cursor.fetchone()
    if not row:
        return None

    return PaperStatusResponse(
        paper_id=row["paper_id"],
        title=row["title"],
        arxiv_id=row["arxiv_id"],
        version=row["version"],
        lexical_ready=bool(row["lexical_ready"]),
        semantic_ready=bool(row["semantic_ready"]),
        indexing_error=row["indexing_error"],
    )


def delete_paper(
    paper_id: str,
    owner_id: str,
    db_path: Optional[str] = None,
) -> bool:
    """Delete paper and all associated passages/runs belonging to owner, cancelling active tasks."""
    from backend.app.agent.runs import cancel_paper_runs
    cancel_paper_runs(paper_id, owner_id, db_path)

    with transaction(db_path) as conn:
        cursor = conn.execute(
            "SELECT paper_id FROM papers WHERE paper_id = ? AND owner_id = ?",
            (paper_id, owner_id),
        )
        if not cursor.fetchone():
            return False

        conn.execute("DELETE FROM runs WHERE paper_id = ? AND owner_id = ?", (paper_id, owner_id))
        conn.execute("DELETE FROM papers WHERE paper_id = ? AND owner_id = ?", (paper_id, owner_id))

    # Remove from memory caches
    _bm25_cache.pop((owner_id, paper_id), None)
    _chunks_cache.pop((owner_id, paper_id), None)
    _vectors_cache.pop((owner_id, paper_id), None)
    return True


def get_paper_chunks(
    paper_id: str,
    owner_id: str,
    db_path: Optional[str] = None,
) -> List[PassageChunk]:
    """Retrieve chunks for a paper, loading from SQLite into memory if needed."""
    cache_key = (owner_id, paper_id)
    if cache_key in _chunks_cache:
        return _chunks_cache[cache_key]

    conn = get_connection(db_path)
    # Check paper exists and is owned by owner
    cursor = conn.execute(
        "SELECT paper_id FROM papers WHERE paper_id = ? AND owner_id = ?",
        (paper_id, owner_id),
    )
    if not cursor.fetchone():
        return []

    p_cursor = conn.execute(
        """
        SELECT passage_id, parent_passage_id, paper_id, section_id,
               section_path, paragraph_order, text, source_locator,
               offset_start, offset_end, fingerprint
        FROM passages
        WHERE paper_id = ?
        ORDER BY paragraph_order ASC, offset_start ASC
        """,
        (paper_id,),
    )
    chunks = []
    for r in p_cursor.fetchall():
        locator_dict = json.loads(r["source_locator"])
        chunks.append(
            PassageChunk(
                passage_id=r["passage_id"],
                parent_passage_id=r["parent_passage_id"],
                paper_id=r["paper_id"],
                section_id=r["section_id"],
                section_path=r["section_path"],
                paragraph_order=r["paragraph_order"],
                text=r["text"],
                locator=SourceLocation(**locator_dict),
                offset_start=r["offset_start"],
                offset_end=r["offset_end"],
                fingerprint=r["fingerprint"] if "fingerprint" in r.keys() else None,
            )
        )

    _chunks_cache[cache_key] = chunks
    return chunks


def get_bm25_index(
    paper_id: str,
    owner_id: str,
    db_path: Optional[str] = None,
) -> Optional[BM25Index]:
    """Retrieve or build in-memory BM25Index for a paper."""
    cache_key = (owner_id, paper_id)
    if cache_key in _bm25_cache:
        return _bm25_cache[cache_key]

    chunks = get_paper_chunks(paper_id, owner_id, db_path)
    if not chunks:
        return None

    index = BM25Index(chunks)
    _bm25_cache[cache_key] = index
    return index


def store_paper_vectors(
    paper_id: str,
    owner_id: str,
    vectors: Dict[str, List[float]],
    model_id: str = "intfloat/e5-large-v2",
    db_path: Optional[str] = None,
) -> None:
    """Persist dense passage vectors into SQLite and update memory cache."""
    now = get_current_timestamp()
    with transaction(db_path) as conn:
        for passage_id, vec in vectors.items():
            blob = json.dumps(vec).encode("utf-8")
            conn.execute(
                """
                INSERT OR REPLACE INTO vectors (
                    passage_id, paper_id, owner_id, model_id, embedding, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (passage_id, paper_id, owner_id, model_id, blob, now),
            )
        conn.execute(
            "UPDATE papers SET semantic_ready = 1, updated_at = ? WHERE paper_id = ? AND owner_id = ?",
            (now, paper_id, owner_id),
        )

    cache_key = (owner_id, paper_id)
    if cache_key not in _vectors_cache:
        _vectors_cache[cache_key] = {}
    _vectors_cache[cache_key].update(vectors)


def get_paper_vectors(
    paper_id: str,
    owner_id: str,
    db_path: Optional[str] = None,
) -> Dict[str, List[float]]:
    """Retrieve dense vectors for a paper, loading from SQLite into memory cache if needed."""
    cache_key = (owner_id, paper_id)
    if cache_key in _vectors_cache:
        return _vectors_cache[cache_key]

    conn = get_connection(db_path)
    cursor = conn.execute(
        "SELECT passage_id, embedding FROM vectors WHERE paper_id = ? AND owner_id = ?",
        (paper_id, owner_id),
    )
    rows = cursor.fetchall()
    vectors: Dict[str, List[float]] = {}
    for row in rows:
        raw_blob = row["embedding"]
        if isinstance(raw_blob, bytes):
            vec = json.loads(raw_blob.decode("utf-8"))
        elif isinstance(raw_blob, str):
            vec = json.loads(raw_blob)
        else:
            continue
        vectors[row["passage_id"]] = vec

    if vectors:
        _vectors_cache[cache_key] = vectors

    return vectors
