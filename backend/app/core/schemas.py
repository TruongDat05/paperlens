"""Define shared paper, passage, and retrieval data.

Define Paper, Section, Passage, and EvidenceResult for the backend and
QASPER. A Passage carries its own ID, parent_passage_id when split, and
a source location for HTML or QASPER.

Define HTTP schemas for session, ingest, and retrieve. The agent's
action, observation, and answer types live in agent/schemas.py.
"""
