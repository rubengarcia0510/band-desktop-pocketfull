"""`GET /restaurants`, `GET /restaurants/{id}` and `GET /availability` (§8)."""
import pytest

import fixtures as fx
from harness.http import assert_error, assert_status

pytestmark = pytest.mark.stage(1)


def test_restaurant_detail_carries_the_fixture_shape(world, anon):
    body = assert_status(anon.get(f"/restaurants/{world.rid}"), 200).json()
    for field in ("slot_minutes", "reservation_duration_minutes",
                  "cancellation_cutoff_minutes"):
        assert body[field] == world.restaurant[field], field
    assert {t["id"] for t in body["tables"]} == set(world.tables)
    assert len(body["opening_hours"]) == len(world.restaurant["opening_hours"])


def test_unknown_restaurant_is_404(world, anon):
    assert_error(anon.get("/restaurants/r_nope"), 404, "not_found")


def _availability(client, rid, date, party_size):
    return client.get("/availability", params={
        "restaurant_id": rid, "date": date, "party_size": party_size})


def test_starts_at_local_is_the_full_local_timestamp(world, anon):
    slot = _availability(anon, world.rid, world.date, 2).json()["slots"][0]
    assert slot["starts_at_local"] == fx.local(world.date, "18:00")
    assert slot["starts_at"].startswith(f"{world.date}T18:00:00")


def test_booked_table_leaves_the_slot_and_every_overlapping_one(world, book, anon):
    """Duration is 90 minutes on a 30-minute grid, so one booking covers three slots."""
    assert_status(book(table_id="t_2", at="19:00"), 201)
    by_time = {s["starts_at_local"].split("T")[1]: s["available_table_ids"]
               for s in _availability(anon, world.rid, world.date, 4).json()["slots"]}
    for overlapping in ("18:00", "18:30", "19:00", "19:30", "20:00"):
        assert "t_2" not in by_time[overlapping], f"t_2 still offered at {overlapping}"
    assert "t_2" in by_time["20:30"], "20:30 does not overlap a 19:00-20:30 booking"


def test_slot_with_no_free_table_still_appears(world, book, anon):
    for table in ("t_2", "t_3"):
        assert_status(book(table_id=table, at="19:00"), 201)
    slot = next(s for s in _availability(anon, world.rid, world.date, 4).json()["slots"]
                if s["starts_at_local"].endswith("19:00"))
    assert slot["available_table_ids"] == []


def test_closed_day_returns_no_slots(reset, anon):
    """A weekday with no opening_hours entry is closed."""
    date = fx.booking_date()
    closed = [h for h in fx.all_week() if h["weekday"] != fx.weekday_of(date)]
    reset(fx.fixture(restaurants=[fx.restaurant(opening_hours=closed)]))
    assert _availability(anon, "r_anker", date, 2).json()["slots"] == []


@pytest.mark.parametrize("drop", ["restaurant_id", "date", "party_size"])
def test_availability_requires_all_three_parameters(world, anon, drop):
    params = {"restaurant_id": world.rid, "date": world.date, "party_size": 2}
    params.pop(drop)
    assert_error(anon.get("/availability", params=params), 422, "validation_failed")


@pytest.mark.parametrize("date", ["2026-02-30", "not-a-date", "24-09-2026"])
def test_availability_rejects_unparseable_dates(world, anon, date):
    """An unparseable date is out of range, not a type error: 422 (§5)."""
    assert_error(_availability(anon, world.rid, date, 2), 422, "validation_failed")


@pytest.mark.parametrize("party", ["0", "-1", "abc", "1e9"])
def test_availability_rejects_bad_party_size(world, anon, party):
    assert_error(_availability(anon, world.rid, world.date, party), 422, "validation_failed")


def test_availability_unknown_restaurant_is_404(world, anon):
    assert_error(_availability(anon, "r_nope", world.date, 2), 404, "not_found")


def test_unknown_query_parameters_are_ignored(world, anon):
    resp = anon.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": 2,
        "sort": "whatever", "page": "3"})
    assert_status(resp, 200)
