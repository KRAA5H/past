"""
conftest.py — shared fixtures for the Chronos backend test suite.

Adds the backend/ directory to sys.path so that 'import models',
'import scene_planner', etc. work from any test file.
"""
from __future__ import annotations

import os
import sys

# Ensure backend/ is on the import path
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest
from sqlmodel import SQLModel, create_engine, Session
from unittest.mock import MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# API key fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_api_key() -> str:
    return "test-api-key-00000000"


# ---------------------------------------------------------------------------
# In-memory SQLite engine (overrides the module-level engine in models.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_engine(monkeypatch):
    """
    Creates a fresh in-memory SQLite engine, swaps it into models.engine,
    creates all tables, and tears down after the test.
    """
    import models

    engine = create_engine("sqlite:///:memory:", echo=False)
    monkeypatch.setattr(models, "engine", engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def db_session(mem_engine):
    """Yields an open SQLModel Session against the in-memory engine."""
    with Session(mem_engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Mock Gemini generate_content response builder
# ---------------------------------------------------------------------------


def make_fc_response(*function_calls: tuple[str, dict]):
    """
    Build a mock generate_content response that contains one candidate
    with one part per (name, args) pair in *function_calls*.

    Usage::

        resp = make_fc_response(
            ("set_scene_description", {"description": "Rome", "lighting": "day"}),
            ("place_npc", {"npc_id": "caesar", "name": "Julius Caesar"}),
        )
    """
    parts = []
    for name, args in function_calls:
        fc = MagicMock()
        fc.name = name
        fc.args = args
        part = MagicMock()
        part.function_call = fc
        parts.append(part)

    candidate = MagicMock()
    candidate.content.parts = parts

    response = MagicMock()
    response.candidates = [candidate]
    return response


# ---------------------------------------------------------------------------
# Mock Gemini client (sync, for ScenePlanner)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_genai_client(monkeypatch):
    """
    Patches scene_planner.genai.Client so no real HTTP calls are made.
    Returns the mock client instance.
    """
    import scene_planner

    client = MagicMock()
    monkeypatch.setattr(scene_planner.genai, "Client", lambda **kw: client)
    return client


# ---------------------------------------------------------------------------
# Mock async Gemini client (for GeminiLiveSession)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_live_client(monkeypatch):
    """
    Patches gemini_live.genai.Client and sets up the async context manager
    chain required by GeminiLiveSession.start().

    Returns (mock_client, mock_session) where mock_session is the object
    returned by __aenter__ of the live.connect() context manager.
    """
    import gemini_live

    mock_session = AsyncMock()
    # session.receive() must be an async generator — default is empty
    async def _empty_receive():
        return
        yield  # make it a generator

    mock_session.receive = _empty_receive

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    client = MagicMock()
    client.aio.live.connect.return_value = mock_cm

    monkeypatch.setattr(gemini_live.genai, "Client", lambda **kw: client)
    return client, mock_session
