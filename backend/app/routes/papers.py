"""Expose endpoints for managing a user's papers.

Register POST /api/v1/papers/ingest, GET
/api/v1/papers/{paper_id}/status, and DELETE /api/v1/papers/{paper_id}.
Derive the owner from the authenticated session. Return HTTP 202 with
paper_id and index_status while ingestion is in progress.

Delegate ingestion and status lookup to their respective modules. On
deletion, remove the paper, index, and related runs, and prevent pending
tasks from writing the data back.
"""
