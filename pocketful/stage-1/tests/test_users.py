"""ST-1.2: User + balance + auth tests."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_signup_creates_user_with_derived_handle(client, fresh_db):
    r = await client.post(
        "/auth/signup",
        json={
            "email": "ada.lovelace@example.com",
            "password": "correct horse",
            "display_name": "Ada",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["display_name"] == "Ada"
    assert body["user_id"].startswith("u_")
    assert body["token"]


async def test_signup_short_password_is_rejected(client, fresh_db):
    r = await client.post(
        "/auth/signup",
        json={"email": "a@example.com", "password": "short", "display_name": "A"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_signup_invalid_email_is_rejected(client, fresh_db):
    r = await client.post(
        "/auth/signup",
        json={"email": "no-at-sign", "password": "correct horse", "display_name": "A"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_signup_duplicate_email_returns_email_taken(client, fresh_db):
    payload = {"email": "ada@example.com", "password": "correct horse", "display_name": "Ada"}
    r1 = await client.post("/auth/signup", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/auth/signup", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "email_taken"


async def test_signup_malformed_json_returns_400(client, fresh_db):
    """spec §5: unparseable body -> 400 malformed_request."""
    r = await client.post(
        "/auth/signup",
        content=b"{not valid json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "malformed_request"


async def test_signup_wrong_field_type_returns_400(client, fresh_db):
    """spec §5: a field of the wrong JSON type -> 400 malformed_request."""
    r = await client.post(
        "/auth/signup",
        json={"email": "x@example.com", "password": 12345, "display_name": "X"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "malformed_request"


async def test_signup_derived_handle_taken_returns_handle_taken(client, fresh_db):
    r1 = await client.post(
        "/auth/signup",
        json={"email": "ada@example.com", "password": "correct horse", "display_name": "Ada"},
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/auth/signup",
        json={"email": "ada@example.org", "password": "correct horse", "display_name": "Ada2"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "handle_taken"


async def test_login_returns_token_for_existing_user(client, fresh_db):
    await client.post(
        "/auth/signup",
        json={"email": "bob@example.com", "password": "correct horse", "display_name": "Bob"},
    )
    r = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "correct horse"},
    )
    assert r.status_code == 200
    assert r.json()["token"]


async def test_login_wrong_password_returns_401(client, fresh_db):
    await client.post(
        "/auth/signup",
        json={"email": "bob@example.com", "password": "correct horse", "display_name": "Bob"},
    )
    r = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "wrong horse"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_login_unknown_email_returns_401(client, fresh_db):
    r = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "correct horse"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_me_requires_bearer_token(client, fresh_db):
    r = await client.get("/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_me_returns_balance_after_signup(client, fresh_db):
    signup = await client.post(
        "/auth/signup",
        json={"email": "c@example.com", "password": "correct horse", "display_name": "C"},
    )
    token = signup.json()["token"]
    r = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 0
    assert body["currency"] == "EUR"
    assert body["minor_units"] == 2


async def test_me_with_unknown_token_returns_401(client, fresh_db):
    r = await client.get("/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
