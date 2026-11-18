"""Specify tests for paper ingestion, status, and deletion.

Use local SQLite and fake adapters to test ownership, input limits,
repeated ingestion, and the lexical_ready and semantic_ready states.

Cover embedding batches interrupted by a restart and paper deletion
while a task is still running.
"""
