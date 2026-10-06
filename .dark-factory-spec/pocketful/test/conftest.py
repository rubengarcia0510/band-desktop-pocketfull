"""Track-level pytest configuration for `pocketful`."""
from __future__ import annotations

import pathlib
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402
from harness.http import Api, new_key  # noqa: E402



@pytest.fixture
def world(reset, api):
    """Ada (10000), Bob (2500) and Cy (500), all signed in."""
    fixture = fx.fixture()
    reset(fixture)
    return SimpleNamespace(
        fixture=fixture,
        total=fx.seeded_total(fixture),
        currency=fixture["currency"],
        minor_units=fixture["minor_units"],
        ada=api().authenticate(fx.ADA["email"], fx.ADA["password"]),
        bob=api().authenticate(fx.BOB["email"], fx.BOB["password"]),
        cy=api().authenticate(fx.CY["email"], fx.CY["password"]),
    )


@pytest.fixture
def balance():
    """One wallet's balance, read the only way the spec allows: GET /me."""
    def _balance(client) -> int:
        resp = client.get("/me")
        assert resp.status_code == 200, resp.text
        return resp.json()["balance"]
    return _balance


@pytest.fixture
def conservation(balance):
    """Sum every wallet and compare against the seeded total.

    There is no administrative endpoint, so this logs in as each seeded user --
    exactly how the spec says the harness checks it.
    """
    def _check(world_, clients=None):
        clients = clients or [world_.ada, world_.bob, world_.cy]
        total = sum(balance(c) for c in clients)
        assert total == world_.total, (
            f"money was created or destroyed: {total} != seeded {world_.total}")
        return total
    return _check


@pytest.fixture
def pay(world):
    def _pay(client=None, *, to_handle="bob", amount=100, key=None, **extra):
        body = {"to_handle": to_handle, "amount": amount}
        body.update(extra)
        return (client or world.ada).post(
            "/payments", json=body,
            idempotency_key=new_key() if key is None else key)
    return _pay


@pytest.fixture
def ask(world):
    """Create a request. The caller is the requester."""
    def _ask(client=None, *, payer_handle="ada", amount=1200, key=None, **extra):
        body = {"payer_handle": payer_handle, "amount": amount}
        body.update(extra)
        return (client or world.bob).post(
            "/requests", json=body,
            idempotency_key=new_key() if key is None else key)
    return _ask
