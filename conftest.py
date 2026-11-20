"""Isolate every test suite before importing application modules."""
import os
import tempfile

_test_root = tempfile.TemporaryDirectory(prefix="paperlens-tests-")
os.environ["DB_PATH"] = os.path.join(_test_root.name, "tests.db")
os.environ["MOCK_PROVIDERS"] = "true"

from backend.tests.conftest import clean_test_db  # noqa: E402,F401
