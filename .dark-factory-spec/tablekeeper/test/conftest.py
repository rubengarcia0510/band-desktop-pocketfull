"""Track-level pytest configuration for `tablekeeper`."""
from __future__ import annotations

import pathlib
import sys
from types import SimpleNamespace

import pytest

# The harness package lives at the repository root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402



@pytest.fixture
def world(reset, api):
    """The default seeded world: one restaurant, three tables, Ada and Bob.

    Returns the fixture plus two authenticated clients and the booking date the
    tests use, so a test says what it is checking rather than how it got set up.
    """
    fixture = fx.fixture()
    reset(fixture)
    restaurant = fixture["restaurants"][0]
    return SimpleNamespace(
        fixture=fixture,
        restaurant=restaurant,
        rid=restaurant["id"],
        timezone=restaurant["timezone"],
        tables={t["id"]: t for t in restaurant["tables"]},
        date=fx.booking_date(restaurant["timezone"]),
        ada=api().authenticate(fx.ADA["email"], fx.ADA["password"]),
        bob=api().authenticate(fx.BOB["email"], fx.BOB["password"]),
    )


@pytest.fixture
def book(world):
    """Create a reservation, defaulting to a free table and a valid slot."""
    from harness.http import new_key

    def _book(client=None, *, table_id="t_2", at="19:00", party_size=4,
              key=None, restaurant_id=None, starts_at_local=None, **extra):
        body = {
            "restaurant_id": world.rid if restaurant_id is None else restaurant_id,
            "table_id": table_id,
            "starts_at_local": starts_at_local or fx.local(world.date, at),
            "party_size": party_size,
        }
        body.update(extra)
        return (client or world.ada).post(
            "/reservations", json=body, idempotency_key=new_key() if key is None else key)
    return _book
