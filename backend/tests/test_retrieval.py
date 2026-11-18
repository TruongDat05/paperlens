"""Specify correctness tests for retrieval configurations B1 to B4.

Use fixed questions, passages, vectors, and scores to check RRF and
rerank order, source locations, and grouping by parent paragraph.

Check configured top-k, BM25 fallback on provider failure, and the mode
reported in EvidenceResult.
"""
