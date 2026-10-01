"""Shared pytest fixtures.

Spins up the FastAPI app against an isolated SQLite file per test session
so reset semantics are observable without touching the container default.
"""

from __future__ import annotations

import os
import tempfile
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import db as db_mod
from app.main import app


@pytest.fixture(scope="session")
def db_path() -> str:
    fd, path = tempfile.mkstemp(prefix="pocketful-test-", suffix=".db")
    os.close(fd)
    if os.path.exists(path):
        os.remove(path)
    return path


@pytest.fixture(scope="session", autouse=True)
def _bind_db(db_path: str) -> None:
    os.environ["POCKETFUL_DB_PATH"] = db_path
    db_mod.reset_connection_for_tests(db_path)
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def fresh_db(db_path: str) -> AsyncIterator[None]:
    """Reset to an empty database between tests that need a clean slate."""
    db_mod.reset_connection_for_tests(db_path)
    yield
