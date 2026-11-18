"""Expose POST /api/v1/retrieve for Evidence Mode.

Authenticate the owner and check access to paper_id. Validate the
question, top-k, and index readiness before passing the loaded paper and
index to the retrieval engine.

Return EvidenceResult with source passages, ranks, retrieval_mode, and
fallback_reason when applicable. Return the appropriate status while
indexing is in progress so the side panel can keep polling.
"""
