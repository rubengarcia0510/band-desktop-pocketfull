"""POST /requests/{id}/pay tests (spec §8)."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_pay_request_success(client, fresh_db):
    """1. Valid authenticated request returns 201 with payment."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 1200, "note": "taxi"},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-001"},
    )
    assert r.status_code == 201
    request_id = r.json()["request_id"]

    r = await client.post(
        f"/requests/{request_id}/pay",
        json={"visibility": "private"},
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-001"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["from_user_id"] == "u_ada"
    assert body["from_handle"] == "ada"
    assert body["to_user_id"] == "u_bob"
    assert body["to_handle"] == "bob"
    assert body["amount"] == 1200
    assert body["currency"] == "EUR"
    assert body["visibility"] == "private"
    assert body["request_id"] == request_id
    assert "payment_id" in body
    assert "created_at" in body


async def test_pay_request_balances_updated(client, fresh_db):
    """2. Balances are updated atomically after pay."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 3000},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-bal"},
    )
    request_id = r.json()["request_id"]

    await client.post(
        f"/requests/{request_id}/pay",
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-bal"},
    )

    me_ada = await client.get("/me", headers={"Authorization": f"Bearer {token_ada}"})
    assert me_ada.json()["balance"] == 7000

    me_bob = await client.get("/me", headers={"Authorization": f"Bearer {token_bob}"})
    assert me_bob.json()["balance"] == 3000


async def test_pay_request_idempotency_replay_same_body(client, fresh_db):
    """3. Replay with same key and same body returns 200, no duplicate payment."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-replay"},
    )
    request_id = r.json()["request_id"]

    r1 = await client.post(
        f"/requests/{request_id}/pay",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-replay"},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/requests/{request_id}/pay",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-replay"},
    )
    assert r2.status_code == 200
    assert r1.json() == r2.json()

    from app.db import get_connection
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS c FROM payments WHERE request_id = ?", (request_id,)).fetchone()["c"]
    assert n == 1, "payment should not be duplicated"


async def test_pay_request_idempotency_different_body(client, fresh_db):
    """4. Same key, different body returns 409 idempotency_key_reuse."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-body"},
    )
    request_id = r.json()["request_id"]

    r1 = await client.post(
        f"/requests/{request_id}/pay",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-body"},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/requests/{request_id}/pay",
        json={"visibility": "private"},
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-body"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "idempotency_key_reuse"


async def test_pay_request_not_pending(client, fresh_db):
    """5. Paying a non-pending request returns 409 request_not_pending."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-pending"},
    )
    request_id = r.json()["request_id"]

    await client.post(
        f"/requests/{request_id}/pay",
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-pending"},
    )

    r = await client.post(
        f"/requests/{request_id}/pay",
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-again"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "request_not_pending"


async def test_pay_request_insufficient_funds(client, fresh_db):
    """6. Insufficient funds returns 409 insufficient_funds."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-funds"},
    )
    request_id = r.json()["request_id"]

    r = await client.post(
        f"/requests/{request_id}/pay",
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-funds"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "insufficient_funds"


async def test_pay_request_not_payer(client, fresh_db):
    """7. Only the payer can pay returns 403 forbidden."""
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
            {
                "id": "u_cy",
                "email": "cy@example.com",
                "password": "correct horse",
                "display_name": "Cy",
                "handle": "cy",
                "balance": 0,
            },
        ],
        "payments": [],
        "requests": [],
    }
    await client.post("/_test/reset", json=fixture)

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    login_cy = await client.post(
        "/auth/login",
        json={"email": "cy@example.com", "password": "correct horse"},
    )
    token_cy = login_cy.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-forb"},
    )
    request_id = r.json()["request_id"]

    r = await client.post(
        f"/requests/{request_id}/pay",
        headers={"Authorization": f"Bearer {token_cy}", "Idempotency-Key": "pay-forb"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


async def test_pay_request_not_found(client, fresh_db):
    """8. Unknown request returns 404 not_found."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    r = await client.post(
        "/requests/rq_nonexistent/pay",
        headers={"Authorization": f"Bearer {token_ada}", "Idempotency-Key": "pay-404"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_pay_request_missing_idempotency_key(client, fresh_db):
    """9. Missing Idempotency-Key returns 400 missing_idempotency_key."""
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

    login_ada = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "correct horse"},
    )
    token_ada = login_ada.json()["token"]

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-key"},
    )
    request_id = r.json()["request_id"]

    r = await client.post(
        f"/requests/{request_id}/pay",
        headers={"Authorization": f"Bearer {token_ada}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "missing_idempotency_key"


async def test_pay_request_unauthenticated(client, fresh_db):
    """10. No token returns 401."""
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

    login_bob = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    token_bob = login_bob.json()["token"]

    r = await client.post(
        "/requests",
        json={"payer_handle": "ada", "amount": 500},
        headers={"Authorization": f"Bearer {token_bob}", "Idempotency-Key": "req-auth"},
    )
    request_id = r.json()["request_id"]

    r = await client.post(
        f"/requests/{request_id}/pay",
        headers={"Idempotency-Key": "pay-no-auth"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"
