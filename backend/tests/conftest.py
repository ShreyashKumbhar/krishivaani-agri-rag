"""Pytest fixtures for the KrishiVaani backend.

The test database is isolated from the development database so running the
suite never deletes local demo history.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_DB = BACKEND_ROOT / "data" / "test_agrivaani.db"

os.environ["AGRI_DB_PATH"] = str(TEST_DB)
os.environ.setdefault("LLM_PROVIDER", "template")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashed")
os.environ.setdefault("MANDI_PROVIDER", "demo")
os.environ.setdefault("TTS_PROVIDER", "edge")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    if TEST_DB.exists():
        TEST_DB.unlink()
    with TestClient(app) as test_client:
        yield test_client
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture(scope="session")
def services(client):
    return client.app.state.services
