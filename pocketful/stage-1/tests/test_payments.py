"""POST /payments tests (spec §7, §8)."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_create_payment_success(client, fresh_db):
    """1. Valid authenticated request returns 201 with exact spec response."""
    from datetime import datetime, timezone

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
                "balance": 0,
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
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 1500, "note": "dinner", "visibility": "public"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-001"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["from_user_id"] == "u_ada"
    assert body["from_handle"] == "ada"
    assert body["to_user_id"] == "u_bob"
    assert body["to_handle"] == "bob"
    assert body["amount"] == 1500
    assert body["currency"] == "EUR"
    assert body["note"] == "dinner"
    assert body["visibility"] == "public"
    assert body["request_id"] is None
    assert "payment_id" in body
    assert "created_at" in body


async def test_payment_idempotency_replay_same_body(client, fresh_db):
    """2. Replay with same key and same body returns 200, no duplicate payment."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r1 = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500, "note": "coffee", "visibility": "public"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-replay"},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500, "note": "coffee", "visibility": "public"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-replay"},
    )
    assert r2.status_code == 200
    assert r1.json() == r2.json()

    from app.db import get_connection

    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
    assert n == 1, "payment should not be duplicated"


async def test_payment_idempotency_different_body(client, fresh_db):
    """3. Same key, different body returns 409 idempotency_key_reuse."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r1 = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500, "note": "coffee"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-body-test"},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 600, "note": "different"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-body-test"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "idempotency_key_reuse"


async def test_payment_validation_insufficient_funds(client, fresh_db):
    """4a. Insufficient funds returns 409 insufficient_funds."""
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
                "balance": 100,
            },
            {
                "id": "u_bob",
                "email": "bob@example.com",
                "password": "correct horse",
                "display_name": "Bob",
                "handle": "bob",
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-no-funds"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "insufficient_funds"


async def test_payment_validation_self_payment(client, fresh_db):
    """4b. Self-payment returns 422 self_payment."""
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
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-self"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "self_payment"


async def test_payment_validation_invalid_amount(client, fresh_db):
    """4c. Invalid amount returns 422 validation_failed."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": -1},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-neg"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_payment_validation_note_too_long(client, fresh_db):
    """4d. Note > 200 chars returns 422 validation_failed."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500, "note": "x" * 201},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-note"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_payment_validation_invalid_visibility(client, fresh_db):
    """4e. Invalid visibility returns 422 validation_failed."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500, "visibility": "invalid"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-vis"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_payment_validation_recipient_not_found(client, fresh_db):
    """4f. Unknown recipient returns 404 not_found."""
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
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "nobody", "amount": 500},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-404"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_payment_missing_idempotency_key(client, fresh_db):
    """4g. Missing Idempotency-Key returns 400 missing_idempotency_key."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "missing_idempotency_key"


async def test_payment_unauthenticated(client, fresh_db):
    """4h. No token returns 401."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 500},
        headers={"Idempotency-Key": "key-no-auth"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_payment_balances_updated_atomically(client, fresh_db):
    """5. Payment updates balances atomically (no partial state)."""
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
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/payments",
        json={"to_handle": "bob", "amount": 3000},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "key-balance"},
    )
    assert r.status_code == 201

    me_ada = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me_ada.json()["balance"] == 7000

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]
    me_bob = await client.get("/me", headers={"Authorization": f"Bearer {token_bob}"})
    assert me_bob.json()["balance"] == 3000
