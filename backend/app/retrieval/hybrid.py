"""Coordinate retrieval configurations B1 through B4.

Accept a question, one paper's index, and configuration. B1 uses BM25,
B2 uses E5, B3 fuses both rankings with RRF, and B4 reranks the fused
candidates with BGE.

Keep the pre-rerank order for Candidate Recall@20. Keep the best hit for
each parent_passage_id and return the top-k original paragraphs. Return
EvidenceResult with retrieval_mode and the reason for a BM25 fallback
when the product configuration allows it.
"""
