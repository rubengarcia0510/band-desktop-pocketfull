"""Stage 3 sample — the shipped smoke checks.

This is a sample, not the graded suite. It shows the shape of each surface once so a
band can wire a service up and iterate; it is roughly a fifth of what is run against
your submission, and every rule it does not reach is in `stage-3.md`.

What it never asks: whether a rule that holds is still reported for a table that some
other rule already excluded, what a `PATCH` records when it changes nothing, and what
a reservation's history looks like to anyone but its owner.
"""
import pytest

import fixtures as fx
from harness.http import assert_status, new_key

pytestmark = pytest.mark.stage(3)


def test_booking_carries_the_effective_policy_and_decision(reset, api):
    reset(fx.fixture(restaurants=[fx.managed_restaurant()]))
    ada = api().authenticate(fx.ADA['email'], fx.ADA['password'])
    date = fx.booking_date()
    published = assert_status(ada.post('/restaurants/r_anker/policies',
        json=fx.policy(date, reservation_duration_minutes=60), idempotency_key=new_key()), 201).json()
    booking = assert_status(ada.post('/reservations', json={
        'restaurant_id': 'r_anker', 'table_id': 't_2',
        'starts_at_local': fx.local(date), 'party_size': 4}, idempotency_key=new_key()), 201).json()
    assert booking['accepted_terms']['policy_version'] == published['policy_version'] == 1
    assert booking['accepted_terms']['reservation_duration_minutes'] == 60
    decision = assert_status(ada.get('/reservations/' + booking['reference'] + '/decision'), 200).json()
    assert decision['revision'] == booking['revision'] == 1
    assert decision['accepted_terms'] == booking['accepted_terms']


def test_explain_accounts_for_every_table(world, anon):
    body = assert_status(anon.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date,
        "party_size": 4, "explain": "true"}), 200).json()
    slot = body["slots"][0]
    assert [e["table_id"] for e in slot["explain"]] \
        == [t["id"] for t in world.restaurant["tables"]]
    for entry in slot["explain"]:
        assert [r["rule"] for r in entry["rules"]] == ["capacity", "no_overlap"]


def test_explain_agrees_with_available_table_ids(world, anon):
    body = assert_status(anon.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date,
        "party_size": 4, "explain": "true"}), 200).json()
    slot = body["slots"][0]
    assert [e["table_id"] for e in slot["explain"] if e["available"]] \
        == slot["available_table_ids"]


def test_availability_is_unchanged_without_explain(world, anon):
    body = assert_status(anon.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": 4}), 200).json()
    assert all("explain" not in slot for slot in body["slots"])


def test_history_records_the_creation(world, book):
    created = assert_status(book(table_id="t_2", at="19:00", party_size=4), 201).json()
    entries = assert_status(
        world.ada.get(f"/reservations/{created['reference']}/history"), 200).json()["entries"]
    assert [e["event"] for e in entries] == ["created"]
    assert {c["field"] for c in entries[0]["changes"]} \
        == {"table_id", "starts_at_local", "party_size"}
    assert all(c["from"] is None for c in entries[0]["changes"])


def test_history_records_a_change_with_the_old_value(world, book):
    created = assert_status(book(table_id="t_2", at="19:00"), 201).json()
    ref = created["reference"]
    assert_status(world.ada.patch(f"/reservations/{ref}", json={"table_id": "t_3"}), 200)
    entries = assert_status(
        world.ada.get(f"/reservations/{ref}/history"), 200).json()["entries"]
    assert [e["seq"] for e in entries] == [1, 2]
    assert entries[1]["changes"] == [
        {"field": "table_id", "from": "t_2", "to": "t_3"}]


def test_adopt_one_booking_as_a_recurring_agreement(world, book):
    from harness.http import new_key
    anchor = book().json()
    response = world.ada.post('/series', json=dict(anchor_reference=anchor['reference'],
        count=2, interval_weeks=1), idempotency_key=new_key())
    assert response.status_code == 201
    series = response.json()
    assert len(series['occurrences']) == 2
    assert series['occurrences'][0]['reservation'] == anchor
