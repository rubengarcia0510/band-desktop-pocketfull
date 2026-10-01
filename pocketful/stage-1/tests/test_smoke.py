"""ST-1.1 smoke tests for the runtime contract (spec §3.2, §3.3)."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_health_returns_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_reset_returns_204_and_replaces_state(client):
    r = await client.post(
        "/_test/reset",
        json={
            "currency": "EUR",
            "minor_units": 2,
            "users": [],
            "payments": [],
            "requests": [],
        },
    )
    assert r.status_code == 204
    assert r.content in (b"", b"null")


async def test_health_is_idempotent(client):
    for _ in range(3):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


async def test_required_tables_present_after_reset(client):
    """Subtask 2: confirm the 5 spec-mandated tables exist after /_test/reset."""
    from app.db import get_connection

    r = await client.post(
        "/_test/reset",
        json={
            "currency": "EUR",
            "minor_units": 2,
            "users": [],
            "payments": [],
            "requests": [],
        },
    )
    assert r.status_code == 204
    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    required = {"payments", "payment_requests", "splits", "settlements", "idempotency_keys"}
    missing = required - names
    assert not missing, f"missing tables after reset: {missing}"
