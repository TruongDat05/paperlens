"""Pytest configuration and test isolation fixtures for PaperLens."""

import os
import pytest
from backend.app.core.config import get_settings
from backend.app.core.db import init_db, _local
from backend.app.cache import paper_store


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    """Ensure every test runs against a clean, isolated SQLite database."""
    test_db = str(tmp_path / "test_paperlens.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("MOCK_PROVIDERS", "true")
    monkeypatch.setenv("DAILY_AGENT_TURNS", "5")
    monkeypatch.setenv("DAILY_NEW_INDEXES", "5")
    monkeypatch.setenv("DAILY_SEMANTIC_RETRIEVALS", "20")
    for provider in ('GOOGLE','GITHUB'):
        monkeypatch.setenv(provider+'_CLIENT_ID','')
        monkeypatch.setenv(provider+'_CLIENT_SECRET','')
    monkeypatch.setenv('AUTH_PUBLIC_BASE_URL','http://localhost:8000')

    # Clear settings cache so get_settings() picks up new DB_PATH
    get_settings.cache_clear()

    # Clear thread-local SQLite connections and in-memory caches
    if hasattr(_local, "connections"):
        for conn in _local.connections.values():
            conn.close()
        _local.connections.clear()
    paper_store._bm25_cache.clear()
    paper_store._chunks_cache.clear()
    paper_store._vectors_cache.clear()

    # Initialize tables
    init_db(test_db)
    yield

    # Cleanup
    if hasattr(_local, "connections"):
        for conn in _local.connections.values():
            conn.close()
        _local.connections.clear()
    paper_store._bm25_cache.clear()
    paper_store._chunks_cache.clear()
    paper_store._vectors_cache.clear()
    get_settings.cache_clear()
