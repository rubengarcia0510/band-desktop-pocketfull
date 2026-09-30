"""POST /requests tests (spec §8)."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_create_request_success(client, fresh_db):
    """Valid authenticated request returns 201 with exact spec response."""
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
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    assert login.status_code == 200
    token = login.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 1200, "note": "taxi"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-key-001"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["requester_id"] == "u_bob"
    assert body["requester_handle"] == "bob"
    assert body["payer_id"] == "u_ada"
    assert body["payer_handle"] == "ada"
    assert body["amount"] == 1200
    assert body["currency"] == "EUR"
    assert body["note"] == "taxi"
    assert body["status"] == "pending"
    assert body["payment_id"] is None
    assert "request_id" in body
    assert "created_at" in body


async def test_request_idempotency_replay_same_body(client, fresh_db):
    """Replay with same key and same body returns 200, no duplicate request."""
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
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r1 = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500, "note": "coffee"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-replay"},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500, "note": "coffee"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-replay"},
    )
    assert r2.status_code == 200
    assert r1.json() == r2.json()

    from app.db import get_connection

    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS c FROM payment_requests").fetchone()["c"]
    assert n == 1, "request should not be duplicated"


async def test_request_idempotency_different_body(client, fresh_db):
    """Same key, different body returns 409 idempotency_key_reuse."""
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
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r1 = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500, "note": "coffee"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-body-test"},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 600, "note": "different"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-body-test"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "idempotency_key_reuse"


async def test_request_validation_self_request(client, fresh_db):
    """Self-request returns 422 self_request."""
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
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-self"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "self_request"


async def test_request_validation_invalid_amount(client, fresh_db):
    """Invalid amount returns 422 validation_failed."""
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
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": -1},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-neg"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_request_validation_note_too_long(client, fresh_db):
    """Note > 200 chars returns 422 validation_failed."""
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
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500, "note": "x" * 201},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-note"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_request_validation_recipient_not_found(client, fresh_db):
    """Unknown payer returns 404 not_found."""
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
        "/requests",
        json={"payer_handle": "nobody", "amount": 500},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "req-404"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_request_missing_idempotency_key(client, fresh_db):
    """Missing Idempotency-Key returns 400 missing_idempotency_key."""
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
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token = login.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "missing_idempotency_key"


async def test_request_unauthenticated(client, fresh_db):
    """No token returns 401."""
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
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Idempotency-Key": "req-no-auth"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_list_requests_success(client, fresh_db):
    """GET /requests returns 200 with correct shape."""
    fixture = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [
            {"id": "u_ada", "email": "ada@example.com", "password": "correct horse",
             "display_name": "Ada", "handle": "ada", "balance": 10000},
            {"id": "u_bob", "email": "bob@example.com", "password": "correct horse",
             "display_name": "Bob", "handle": "bob", "balance": 0},
            {"id": "u_cy", "email": "cy@example.com", "password": "correct horse",
             "display_name": "Cy", "handle": "cy", "balance": 0},
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login = await client.post("/auth/login", json={"email": "bob@example.com", "password": "correct horse"})
    token = login.json()["token"]

    await client.post("/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "r1"})
    await client.post("/requests",
        json={"payer_handle": "cy", "amount": 300},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "r2"})

    r = await client.get("/requests", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "requests" in body
    assert "has_more" in body
    assert len(body["requests"]) == 2


async def test_list_requests_unauthenticated(client, fresh_db):
    """GET /requests without token returns 401."""
    r = await client.get("/requests")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_list_requests_direction_incoming(client, fresh_db):
    """GET /requests?direction=incoming returns only requests where caller is payer."""
    fixture = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [
            {"id": "u_ada", "email": "ada@example.com", "password": "correct horse",
             "display_name": "Ada", "handle": "ada", "balance": 10000},
            {"id": "u_bob", "email": "bob@example.com", "password": "correct horse",
             "display_name": "Bob", "handle": "bob", "balance": 0},
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login_bob = await client.post("/auth/login", json={"email": "bob@example.com", "password": "correct horse"})
    token_bob = login_bob.json()["token"]

    login_ada = await client.post("/auth/login", json={"email": "ada@example.com", "password": "correct horse"})
    token_ada = login_ada.json()["token"]

    await client.post("/requests",
        json={"payer_handle": "bob", "amount": 500},
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "inc1"})

    r = await client.get("/requests?direction=incoming", headers={"Authorization": f"Bearer {token_bob}"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["requests"]) == 1
    assert body["requests"][0]["payer_handle"] == "bob"
