"""Stage 4 sample — the shipped smoke checks.

This is a sample, not the graded suite. It shows the shape of each surface once so a
service can be wired up against it; the spec is the contract and the graded checks are
the spec's. Passing everything here means the wiring is right, not that the stage holds.
"""
from types import SimpleNamespace
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

import fixtures as fx
from harness.http import assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(4)

COMBINABLE = [["t_1", "t_2"], ["t_2", "t_3"]]


def restaurant(**over):
    base = fx.restaurant(**over)
    base["combinable"] = COMBINABLE
    return base


@pytest.fixture
def world(reset, api):
    fixture = fx.fixture(restaurants=[restaurant()])
    reset(fixture)
    return SimpleNamespace(
        fixture=fixture, rid="r_anker", date=fx.booking_date(),
        ada=api().authenticate(fx.ADA["email"], fx.ADA["password"]),
        bob=api().authenticate(fx.BOB["email"], fx.BOB["password"]))


def book(client, world, *, table_ids=None, table_id=None, at="19:00",
         party_size=6, key=None, **extra):
    body = {"restaurant_id": world.rid,
            "starts_at_local": fx.local(world.date, at), "party_size": party_size}
    if table_ids is not None:
        body["table_ids"] = table_ids
    if table_id is not None:
        body["table_id"] = table_id
    body.update(extra)
    return client.post("/reservations", json=body,
                       idempotency_key=new_key() if key is None else key)


def options(client, world, party_size, at="19:00"):
    resp = client.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": party_size})
    assert_status(resp, 200)
    return next(s for s in resp.json()["slots"] if s["starts_at_local"].endswith(at))


def test_available_options_lists_singles_then_pairs(world):
    slot = options(world.ada, world, 4)
    got = [(tuple(o["table_ids"]), o["capacity"]) for o in slot["available_options"]]
    assert got == [(("t_2",), 4), (("t_3",), 6), (("t_1", "t_2"), 6), (("t_2", "t_3"), 10)], got


def test_booking_a_declared_pair(world):
    body = assert_status(book(world.ada, world, table_ids=["t_1", "t_2"],
                              party_size=6), 201).json()
    assert body["table_ids"] == ["t_1", "t_2"]
    assert "table_id" not in body, "table_id is omitted when the set has two members"


def test_table_id_is_still_accepted_and_means_a_set_of_one(world):
    body = assert_status(book(world.ada, world, table_id="t_3", party_size=4),
                         201).json()
    assert body["table_ids"] == ["t_3"] and body["table_id"] == "t_3"


def test_combining_is_not_transitive(world):
    """[t_1,t_2] and [t_2,t_3] do not make {t_1,t_3} bookable."""
    assert_error(book(world.ada, world, table_ids=["t_1", "t_3"], party_size=8),
                 422, "combination_not_allowed")


def test_series_clock_time_can_be_changed(world, book):
    from harness.http import new_key
    anchor = book().json()
    made = world.ada.post('/series', json=dict(anchor_reference=anchor['reference'],
        count=2, interval_weeks=1), idempotency_key=new_key())
    assert made.status_code == 201
    response = world.ada.post('/series/' + made.json()['series_id'] + '/amend',
        json=dict(expected_revision=1, from_index=0, local_time='20:00'), idempotency_key=new_key())
    assert response.status_code == 201
    assert all(o['reservation']['starts_at_local'].endswith('T20:00')
               for o in response.json()['occurrences'])


def test_a_closure_preview_returns_a_plan(reset, api):
    reset(fx.fixture(restaurants=[fx.managed_restaurant() | {'combinable': COMBINABLE}]))
    ada = api().authenticate(fx.ADA['email'], fx.ADA['password'])
    date = dt.date.fromisoformat(fx.booking_date())
    def instant(hour):
        return dt.datetime.combine(date, dt.time(hour), tzinfo=ZoneInfo('Europe/Berlin')).isoformat()
    plan = assert_status(ada.post('/restaurants/r_anker/replans', json={
        'table_id': 't_2', 'from': instant(18), 'to': instant(23)}, idempotency_key=new_key()), 201).json()
    assert plan['plan_id'] and plan['assignments'] == []
