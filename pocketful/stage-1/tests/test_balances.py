"""ST-1.2: Balance invariant tests via /_test/reset seeding + /me reading."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_reset_seeds_users_with_balance(client, fresh_db):
    fixture = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [
            {
                "id": "u_ada",
                "email": "ada@example.com",
                "password": "correct horse",
                "display_name": "Ada",
                "handle": "ada",
                "balance": 10000,
            },
            {
                "id": "u_bob",
                "email": "bob@example.com",
                "password": "correct horse",
                "display_name": "Bob",
                "handle": "bob",
                "balance": 2500,
            },
        ],
        "payments": [],
        "requests": [],
    }
    r = await client.post("/_test/reset", json=fixture)
    assert r.status_code == 204

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    assert login.status_code == 200
    me = await client.get(
        "/me", headers={"Authorization": f"Bearer {login.json()['token']}"}
    )
    assert me.status_code == 200
    assert me.json()["balance"] == 10000


async def test_reset_rejects_negative_balance(client, fresh_db):
    fixture = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [
            {
                "id": "u_ada",
                "email": "ada@example.com",
                "password": "correct horse",
                "display_name": "Ada",
                "handle": "ada",
                "balance": -1,
            }
        ],
        "payments": [],
        "requests": [],
    }
    r = await client.post("/_test/reset", json=fixture)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_reset_supports_three_currencies(client, fresh_db):
    for currency, minor in (("EUR", 2), ("JPY", 0), ("BHD", 3)):
        r = await client.post(
            "/_test/reset",
            json={
                "currency": currency,
                "minor_units": minor,
                "users": [],
                "payments": [],
                "requests": [],
            },
        )
        assert r.status_code == 204, f"{currency}/{minor}: {r.text}"


async def test_reset_rejects_invalid_minor_units(client, fresh_db):
    r = await client.post(
        "/_test/reset",
        json={"currency": "EUR", "minor_units": 1, "users": [], "payments": [], "requests": []},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_total_balance_invariant_after_reset(client, fresh_db):
    """Spec §1 invariant 1: sum of balances equals total seeded."""
    fixture = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [
            {
                "id": "u_a",
                "email": "a@example.com",
                "password": "correct horse",
                "display_name": "A",
                "handle": "a",
                "balance": 7000,
            },
            {
                "id": "u_b",
                "email": "b@example.com",
                "password": "correct horse",
                "display_name": "B",
                "handle": "b",
                "balance": 3000,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    expected_total = 7000 + 3000
    seen = 0
    for email, expected in (("a@example.com", 7000), ("b@example.com", 3000)):
        login = await client.post(
            "/auth/login", json={"email": email, "password": "correct horse"}
        )
        me = await client.get(
            "/me", headers={"Authorization": f"Bearer {login.json()['token']}"}
        )
        seen += me.json()["balance"]
        assert me.json()["balance"] == expected
    assert seen == expected_total
