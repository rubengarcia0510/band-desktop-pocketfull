"""Seeded reservations and the cutoff on change (§4, §8).

The fixture format documents seeding confirmed bookings, and the cutoff rule applies
to `PATCH` as well as to cancel. Both are in the spec and neither is in the sample.
"""
import datetime as dt

import pytest

import fixtures as fx
from harness.http import assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(1)


def seeded_reservation(date, *, reference="SEED01", table_id="t_2", at="19:00",
                       user_id="u_ada", party_size=4):
    """A confirmed booking in the fixture's shape: a create body plus the three
    fields §4 adds -- `id`, `reference` and `user_id`."""
    return {"id": "res_seed", "reference": reference, "user_id": user_id,
            "restaurant_id": "r_anker", "table_id": table_id,
            "starts_at_local": fx.local(date, at), "party_size": party_size}


def test_a_seeded_reservation_occupies_its_table(reset, anon):
    date = fx.booking_date()
    reset(fx.fixture(reservations=[seeded_reservation(date)]))
    slots = anon.get("/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 4}).json()["slots"]
    at_seven = next(s for s in slots if s["starts_at_local"].endswith("19:00"))
    assert "t_2" not in at_seven["available_table_ids"], \
        "a seeded booking holds its table, exactly like one made through the API"


def test_a_seeded_reservation_belongs_to_its_user(reset, api):
    date = fx.booking_date()
    reset(fx.fixture(reservations=[seeded_reservation(date)]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    bob = api().authenticate(fx.BOB["email"], fx.BOB["password"])
    body = assert_status(ada.get("/reservations/SEED01"), 200).json()
    assert body["reference"] == "SEED01" and body["status"] == "confirmed"
    assert [r["reference"] for r in ada.get("/reservations").json()["reservations"]] == ["SEED01"]
    assert_error(bob.get("/reservations/SEED01"), 404, "not_found")


def test_a_seeded_reservation_can_be_cancelled_and_frees_its_table(reset, api, anon):
    date = fx.booking_date()
    reset(fx.fixture(reservations=[seeded_reservation(date)]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    assert_status(ada.post("/reservations/SEED01/cancel"), 200)
    slots = anon.get("/availability", params={
        "restaurant_id": "r_anker", "date": date, "party_size": 4}).json()["slots"]
    at_seven = next(s for s in slots if s["starts_at_local"].endswith("19:00"))
    assert "t_2" in at_seven["available_table_ids"]


def test_a_seeded_booking_blocks_the_same_slot_for_someone_else(reset, api):
    date = fx.booking_date()
    reset(fx.fixture(reservations=[seeded_reservation(date)]))
    bob = api().authenticate(fx.BOB["email"], fx.BOB["password"])
    assert_error(bob.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": fx.local(date, "19:00"), "party_size": 4},
        idempotency_key=new_key()), 409, "table_unavailable")


def test_reset_rejects_ids_longer_than_64_characters(reset):
    fixture = fx.fixture(users=[{**fx.ADA, "id": "u" * 65}])
    assert_error(reset(fixture, raw=True), 422, "validation_failed")


@pytest.mark.parametrize("reference", ["x", "lower01", "TOO-LONG-WITH-DASH"])
def test_reset_rejects_invalid_reservation_references(reset, reference):
    date = fx.booking_date()
    fixture = fx.fixture(reservations=[seeded_reservation(date, reference=reference)])
    assert_error(reset(fixture, raw=True), 422, "validation_failed")


def test_cancelling_a_reservation_that_has_already_started_is_refused(reset, api):
    """§8: within the cutoff of `starts_at`, **or later**. A past booking is later."""
    yesterday = (dt.date.fromisoformat(fx.booking_date()) - dt.timedelta(days=8)).isoformat()
    reset(fx.fixture(reservations=[seeded_reservation(yesterday)]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    assert_error(ada.post("/reservations/SEED01/cancel"), 409, "cutoff_passed")


def test_changing_inside_the_cutoff_is_refused(reset, api):
    """§8: `PATCH` carries the same cutoff rule as cancel, against the current start."""
    cutoff = fx.restaurant(cancellation_cutoff_minutes=60 * 24 * 3650)
    reset(fx.fixture(restaurants=[cutoff]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    date = fx.booking_date()
    ref = assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": fx.local(date, "19:00"), "party_size": 4},
        idempotency_key=new_key()), 201).json()["reference"]
    assert_error(ada.patch(f"/reservations/{ref}", json={"table_id": "t_3"}),
                 409, "cutoff_passed")


@pytest.mark.parametrize("party", ["4.0", "+4", " 4"])
def test_a_query_integer_must_be_plain_decimal_digits(world, anon, party):
    """§5: `1e9`, `4.0` and `+4` are 422 whatever their numeric value."""
    assert_error(anon.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": party}),
        422, "validation_failed")
