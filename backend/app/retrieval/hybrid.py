"""Coordinate retrieval configurations B1 through B4.

Accept a question, one paper's index, and configuration. B1 uses BM25,
B2 uses E5, B3 fuses both rankings with RRF, and B4 reranks the fused
candidates with BGE.

Keep the pre-rerank order for Candidate Recall@20. Keep the best hit for
each parent_passage_id and return the top-k original paragraphs. Return
EvidenceResult with retrieval_mode and the reason for a BM25 fallback
when the product configuration allows it.
"""

from typing import Any, Dict, List, Optional, Tuple
from backend.app.core.schemas import (
    PassageChunk,
    EvidenceItem,
    EvidenceResult,
)
from backend.app.retrieval.bm25 import BM25Index


def reciprocal_rank_fusion(
    sparse_ranked: List[Tuple[str, float]],
    dense_ranked: List[Tuple[str, float]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """Fuse sparse and dense rankings using Reciprocal Rank Fusion (RRF).

    Score(d) = sum_{m in {sparse, dense}} 1 / (k + rank_m(d))
    where rank_m is 1-indexed.
    """
    scores: Dict[str, float] = {}

    for rank, (doc_id, _) in enumerate(sparse_ranked, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank))

    for rank, (doc_id, _) in enumerate(dense_ranked, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank))

    fused = list(scores.items())
    # Sort descending by score, tie-break alphabetically by doc_id
    fused.sort(key=lambda x: (-x[1], x[0]))
    return fused


def group_chunks_by_parent(
    scored_chunks: List[Tuple[PassageChunk, float]],
    top_k: int = 5,
) -> List[EvidenceItem]:
    """Group ranked chunks by parent_passage_id, preserving the best hit per parent."""
    seen_parents: Dict[str, EvidenceItem] = {}
    ordered_evidence: List[EvidenceItem] = []

    rank = 1
    for chunk, score in scored_chunks:
        parent_id = chunk.parent_passage_id
        if parent_id not in seen_parents:
            item = EvidenceItem(
                passage_id=parent_id,
                parent_passage_id=parent_id,
                rank=rank,
                score=score,
                section_heading=chunk.section_path.split(" / ")[-1] if " / " in chunk.section_path else chunk.section_path,
                section_path=chunk.section_path,
                text=chunk.text,
                locator=chunk.locator,
                contributing_chunks=[chunk.passage_id],
                fingerprint=chunk.fingerprint,
                section_id=chunk.section_id,
                paper_id=chunk.paper_id,
            )
            seen_parents[parent_id] = item
            ordered_evidence.append(item)
            rank += 1
            if len(ordered_evidence) >= top_k:
                break
        else:
            seen_parents[parent_id].contributing_chunks.append(chunk.passage_id)

    return ordered_evidence


def is_overview_query(query: str) -> bool:
    import re
    import unicodedata
    query = query.split("\nContext:", 1)[0]
    q = "".join(c for c in unicodedata.normalize("NFKD", query.lower()) if not unicodedata.combining(c))
    general = re.search(r"overview|summari|main idea|core idea|tom tat|y tuong|resum|总结|概述|要約", q)
    whole_paper = re.search(r"explain (?:this |the )?(?:paper|article)[.!?]?$|expli\w* (?:cet |ce )article[.!?]?$", q)
    return bool(re.search(r"paper|article|bai|nghien cuu|论文|論文|articulo", q) and (general or whole_paper))


def is_research_extension_query(query: str) -> bool:
    import re
    import unicodedata
    query = query.split("\nContext:", 1)[0]
    q = "".join(c for c in unicodedata.normalize("NFKD", query.lower()) if not unicodedata.combining(c))
    extension_patterns = [
        r"extension|extend|direction|future\s+work|promising|next\s+step",
        r"implementation\s+direction|implement|follow-up|follow\s+up",
        r"related\s+work|related\s+paper|compare\s+with|alternative|other\s+paper",
        r"huong\s+phat\s+trien|mo\s+rong|nghien\s+cuu\s+tiep",
        r"huong\s+moi|huong\s+nghien\s+cuu|tim.*paper|tai\s+lieu\s+lien\s+quan",
        r"paper\s+khac|bai\s+bao\s+khac|nghien\s+cuu\s+khac|paper\s+nao\s+khac|tai\s+lieu\s+khac",
        r"so\s+sanh.*paper|so\s+sanh.*bai\s+bao|link.*paper|link.*bai\s+bao|url.*paper",
        r"arxiv|doi\b",
    ]
    return any(re.search(pat, q) for pat in extension_patterns)


def select_overview_evidence(chunks, ranked, top_k):
    """Mix the abstract, method and conclusion with ranked hits for broad questions."""
    import re
    selected = []
    seen = set()
    def add(chunk, score=1.0):
        if chunk.parent_passage_id not in seen and len(selected) < top_k:
            selected.append((chunk, score))
            seen.add(chunk.parent_passage_id)
    groups = [
        [c for c in chunks if re.search(r"abstract|resume", c.section_path, re.I)],
        [c for c in chunks if re.search(r"method|framework|approach|architecture|construction|retrieval|prompting", c.section_path, re.I)],
        [c for c in chunks if re.search(r"conclusion|limitation|discussion|future", c.section_path, re.I)],
    ]
    for c in groups[0][:2]: add(c)
    for c in groups[1][:1]: add(c)
    for c in groups[2][:1]: add(c)
    if not selected:
        for c, score in ranked: add(c, score)
    return selected


async def retrieve_hybrid(
    query: str,
    chunks: List[PassageChunk],
    bm25_index: Optional[BM25Index] = None,
    mode: str = "B1",
    top_k: int = 5,
    fallback_reason: Optional[str] = None,
    request_id: str = "req-default",
    paper_id: str = "paper-default",
    owner_id: Optional[str] = None,
    fpt_provider: Optional[Any] = None,
    passage_vectors: Optional[Dict[str, List[float]]] = None,
) -> EvidenceResult:
    """Retrieve top-k evidence items for a paper across configurations B1-B4."""
    import asyncio
    from backend.app.providers.fpt import FPTProvider
    from backend.app.retrieval.dense import rank_passages_dense
    from backend.app.cache.paper_store import get_paper_vectors, store_paper_vectors

    from backend.app.core.config import get_settings
    cfg = get_settings().retrieval
    if mode not in {"B1", "B2", "B3", "B4"}:
        raise ValueError("Unknown retrieval mode")
    if not query.strip() or not 1 <= top_k <= 20:
        raise ValueError("Invalid query or evidence limit")
    if not bm25_index and chunks:
        bm25_index = BM25Index(chunks)

    scored_chunks: List[Tuple[PassageChunk, float]] = []
    chunk_map = {c.passage_id: c for c in chunks}
    actual_mode = mode
    actual_fallback = fallback_reason
    candidate_passage_ids: List[str] = []

    async def _resolve_passage_vectors() -> Optional[Dict[str, List[float]]]:
        nonlocal passage_vectors
        if passage_vectors is not None:
            return passage_vectors
        if owner_id:
            stored = get_paper_vectors(paper_id, owner_id)
            if stored:
                passage_vectors = stored
                return passage_vectors
        if chunks:
            fpt = fpt_provider or FPTProvider()
            embedded_vecs = await fpt.get_embeddings([c.text for c in chunks], prefix="passage: ")
            passage_vectors = {c.passage_id: vec for c, vec in zip(chunks, embedded_vecs)}
            if owner_id:
                store_paper_vectors(paper_id, owner_id, passage_vectors)
            return passage_vectors
        return None

    if mode == "B1":
        if bm25_index:
            scored_chunks = bm25_index.search(query, top_k=cfg.sparse_candidates)
        candidate_passage_ids = [c.passage_id for c, _ in scored_chunks]

    elif mode == "B2":
        try:
            fpt = fpt_provider or FPTProvider()
            vecs, q_vecs = await asyncio.gather(
                _resolve_passage_vectors(), fpt.get_embeddings([query], prefix="query: ")
            )
            if not vecs:
                raise RuntimeError("No passage vectors available")
            q_vec = q_vecs[0]
            dense_hits = rank_passages_dense(q_vec, vecs, top_k=cfg.dense_candidates)
            scored_chunks = [(chunk_map[pid], score) for pid, score in dense_hits if pid in chunk_map]
            candidate_passage_ids = [pid for pid, _ in dense_hits]
        except Exception as err:
            actual_mode = "B1"
            actual_fallback = f"Dense retrieval unavailable; fell back to lexical ({err})"
            scored_chunks = bm25_index.search(query, top_k=cfg.sparse_candidates) if bm25_index else []
            candidate_passage_ids = [c.passage_id for c, _ in scored_chunks]

    elif mode == "B3":
        sparse_hits = bm25_index.search(query, top_k=cfg.sparse_candidates) if bm25_index else []
        sparse_pairs = [(c.passage_id, score) for c, score in sparse_hits]
        try:
            fpt = fpt_provider or FPTProvider()
            vecs, q_vecs = await asyncio.gather(
                _resolve_passage_vectors(), fpt.get_embeddings([query], prefix="query: ")
            )
            if not vecs:
                raise RuntimeError("No passage vectors available")
            q_vec = q_vecs[0]
            dense_hits = rank_passages_dense(q_vec, vecs, top_k=cfg.dense_candidates)
            fused = reciprocal_rank_fusion(sparse_pairs, dense_hits, k=cfg.rrf_k)
            scored_chunks = [(chunk_map[pid], score) for pid, score in fused if pid in chunk_map]
            candidate_passage_ids = [pid for pid, _ in fused]
        except Exception as err:
            actual_mode = "B1"
            actual_fallback = f"Dense retrieval unavailable; fell back to lexical ({err})"
            scored_chunks = sparse_hits
            candidate_passage_ids = [c.passage_id for c, _ in sparse_hits]

    elif mode == "B4":
        sparse_hits = bm25_index.search(query, top_k=cfg.sparse_candidates) if bm25_index else []
        sparse_pairs = [(c.passage_id, score) for c, score in sparse_hits]
        b3_succeeded = False
        try:
            fpt = fpt_provider or FPTProvider()
            vecs, q_vecs = await asyncio.gather(
                _resolve_passage_vectors(), fpt.get_embeddings([query], prefix="query: ")
            )
            if not vecs:
                raise RuntimeError("No passage vectors available")
            q_vec = q_vecs[0]
            dense_hits = rank_passages_dense(q_vec, vecs, top_k=cfg.dense_candidates)
            fused = reciprocal_rank_fusion(sparse_pairs, dense_hits, k=cfg.rrf_k)
            scored_chunks = [(chunk_map[pid], score) for pid, score in fused if pid in chunk_map]
            b3_succeeded = True
        except Exception as err:
            actual_fallback = f"Dense retrieval unavailable; fell back to lexical ({err})"
            scored_chunks = sparse_hits

        # Candidate pool before reranking (top 20 for candidate recall@20)
        pre_rerank_pool = scored_chunks[:cfg.rerank_candidates]
        candidate_passage_ids = [c.passage_id for c, _ in pre_rerank_pool]

        # Rerank with BGE
        try:
            fpt = fpt_provider or FPTProvider()
            candidate_texts = [c.text for c, _ in pre_rerank_pool]
            if candidate_texts:
                rerank_scores = await fpt.rerank(query, candidate_texts)
                scored_chunks = [
                    (pre_rerank_pool[idx][0], score)
                    for idx, score in rerank_scores
                    if idx < len(pre_rerank_pool)
                ]
                actual_mode = "B4" if b3_succeeded else "B1+rerank"
            else:
                scored_chunks = pre_rerank_pool
        except Exception as err:
            actual_mode = "B3" if b3_succeeded else "B1"
            actual_fallback = f"Reranker unavailable; fell back to {actual_mode} ({err})"
            scored_chunks = pre_rerank_pool

    if is_overview_query(query) or is_research_extension_query(query):
        scored_chunks = select_overview_evidence(chunks, scored_chunks, top_k)
    evidence = group_chunks_by_parent(scored_chunks, top_k=top_k)

    return EvidenceResult(
        request_id=request_id,
        paper_id=paper_id,
        status="ok",
        retrieval_mode=actual_mode,
        fallback_reason=actual_fallback,
        evidence=evidence,
        candidate_passage_ids=candidate_passage_ids,
    )
