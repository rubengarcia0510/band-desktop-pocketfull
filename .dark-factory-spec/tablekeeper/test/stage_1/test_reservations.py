"""`POST /reservations`, reads, cancel and `PATCH` (§8)."""
import re

import pytest

import fixtures as fx
from harness.http import assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(1)

REFERENCE = re.compile(r"^[A-Z0-9]{6,12}$")


def test_starts_at_carries_an_explicit_offset(world, book):
    """Timestamps are RFC 3339 with an explicit offset (§3.4)."""
    body = book(at="19:00").json()
    for field in ("starts_at", "ends_at", "created_at"):
        assert re.search(r"([+-]\d{2}:\d{2}|Z)$", body[field]), \
            f"{field} = {body[field]!r}"


def test_references_are_unique(world, book):
    refs = {book(table_id=t, at="19:00", party_size=2).json()["reference"]
            for t in ("t_1", "t_2", "t_3")}
    assert len(refs) == 3


def test_overlapping_interval_is_409_not_only_the_same_slot(world, book):
    """The invariant is about intervals, not slot equality."""
    assert_status(book(table_id="t_2", at="19:00"), 201)
    assert_error(book(table_id="t_2", at="20:00"), 409, "table_unavailable")


def test_adjacent_non_overlapping_booking_succeeds(world, book):
    assert_status(book(table_id="t_2", at="19:00"), 201)
    assert_status(book(table_id="t_2", at="20:30"), 201)


def test_a_different_table_at_the_same_time_succeeds(world, book):
    assert_status(book(table_id="t_2", at="19:00"), 201)
    assert_status(book(table_id="t_3", at="19:00"), 201)


@pytest.mark.parametrize("at,code", [
    ("19:15", "not_on_slot_grid"),
    ("18:01", "not_on_slot_grid"),
])
def test_off_grid_start_is_rejected(world, book, at, code):
    assert_error(book(at=at), 422, code)


@pytest.mark.parametrize("at", ["17:00", "23:30"])
def test_outside_opening_hours_is_rejected(world, book, at):
    assert_error(book(at=at), 422, "outside_opening_hours")


def test_reservation_that_would_end_after_closing_is_rejected(world, book):
    """22:00 + 90 minutes runs past a 23:00 close, so the slot never existed."""
    assert_error(book(at="22:00"), 422, "outside_opening_hours")


def test_party_over_table_capacity_is_rejected(world, book):
    assert_error(book(table_id="t_1", party_size=4), 422, "party_exceeds_capacity")


@pytest.mark.parametrize("party", [0, -1, "4", 1.5])
def test_bad_party_size_is_validation_failed(world, book, party):
    assert_error(book(party_size=party), 422, "validation_failed")


def test_unknown_restaurant_or_table_is_404(world, book):
    assert_error(book(restaurant_id="r_nope"), 404, "not_found")
    assert_error(book(table_id="t_nope"), 404, "not_found")


def test_table_from_another_restaurant_is_404(reset, api, world):
    """A real table id, but not this restaurant's."""
    other = fx.restaurant("r_other", name="Other",
                          tables=[{"id": "t_x", "label": "X", "capacity": 4}])
    reset(fx.fixture(restaurants=[world.restaurant, other]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    resp = ada.post("/reservations", json={
        "restaurant_id": world.rid, "table_id": "t_x",
        "starts_at_local": fx.local(world.date, "19:00"), "party_size": 4},
        idempotency_key=new_key())
    assert_error(resp, 404, "not_found")


@pytest.mark.parametrize("value", ["2026-09-24T19:00:00+02:00", "2026-09-24T19:00Z",
                                   "2026-09-24T19:00:00", "not-a-time"])
def test_starts_at_local_must_be_a_bare_local_time(world, book, value):
    assert_error(book(starts_at_local=value), 422, "validation_failed")


def test_malformed_json_is_400(world):
    resp = world.ada.post("/reservations", content="{not json",
                          idempotency_key=new_key())
    assert_error(resp, 400, "malformed_request")


def test_unknown_body_fields_are_ignored(world, book):
    assert_status(book(souvenir="yes", table_id="t_2"), 201)


# ---- reads ---------------------------------------------------------------

def test_list_returns_only_the_callers_reservations(world, book):
    assert_status(book(world.ada, table_id="t_2", at="19:00"), 201)
    assert_status(book(world.bob, table_id="t_3", at="19:00"), 201)
    mine = world.ada.get("/reservations").json()["reservations"]
    assert [r["table_id"] for r in mine] == ["t_2"]


def test_list_is_starts_at_descending(world, book):
    for at in ("18:00", "21:00", "19:30"):
        assert_status(book(table_id="t_2", at=at), 201)
    starts = [r["starts_at"] for r in world.ada.get("/reservations").json()["reservations"]]
    assert starts == sorted(starts, reverse=True)


def test_list_includes_cancelled(world, book):
    ref = book(at="19:00").json()["reference"]
    assert_status(world.ada.post(f"/reservations/{ref}/cancel"), 200)
    statuses = {r["status"] for r in world.ada.get("/reservations").json()["reservations"]}
    assert "cancelled" in statuses


def test_other_peoples_reservations_are_404_not_403(world, book):
    """Do not leak the existence of someone else's booking."""
    ref = book(world.ada, at="19:00").json()["reference"]
    assert_error(world.bob.get(f"/reservations/{ref}"), 404, "not_found")


def test_unknown_reference_is_404(world):
    assert_error(world.ada.get("/reservations/ZZZZZZ"), 404, "not_found")


# ---- cancel --------------------------------------------------------------


def test_cancelling_twice_is_not_an_error(world, book):
    ref = book(at="19:00").json()["reference"]
    assert_status(world.ada.post(f"/reservations/{ref}/cancel"), 200)
    body = assert_status(world.ada.post(f"/reservations/{ref}/cancel"), 200).json()
    assert body["status"] == "cancelled"


def test_cancelling_someone_elses_reservation_is_404(world, book):
    ref = book(world.ada, at="19:00").json()["reference"]
    assert_error(world.bob.post(f"/reservations/{ref}/cancel"), 404, "not_found")


def test_cancel_inside_the_cutoff_is_409(reset, api):
    """cancellation_cutoff_minutes is measured from now to starts_at."""
    # A cutoff wide enough that a booking a week out is still inside it.
    cutoff = fx.restaurant(cancellation_cutoff_minutes=60 * 24 * 3650)
    reset(fx.fixture(restaurants=[cutoff]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    date = fx.booking_date()
    ref = ada.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": fx.local(date, "19:00"), "party_size": 4},
        idempotency_key=new_key()).json()["reference"]
    assert_error(ada.post(f"/reservations/{ref}/cancel"), 409, "cutoff_passed")


# ---- patch ---------------------------------------------------------------


def test_patch_keeps_reference_and_id(world, book):
    created = book(at="19:00").json()
    body = world.ada.patch(f"/reservations/{created['reference']}",
                           json={"starts_at_local": fx.local(world.date, "20:30")}).json()
    assert body["reference"] == created["reference"]
    assert body["reservation_id"] == created["reservation_id"]


def test_patch_needs_no_idempotency_key(world, book):
    ref = book(at="19:00").json()["reference"]
    assert_status(world.ada.patch(f"/reservations/{ref}", json={"party_size": 3}), 200)


def test_patch_validation_matches_create(world, book):
    ref = book(table_id="t_2", at="19:00").json()["reference"]
    assert_error(world.ada.patch(f"/reservations/{ref}",
                                 json={"starts_at_local": fx.local(world.date, "19:15")}),
                 422, "not_on_slot_grid")
    assert_error(world.ada.patch(f"/reservations/{ref}", json={"table_id": "t_1"}),
                 422, "party_exceeds_capacity")
    assert_error(world.ada.patch(f"/reservations/{ref}", json={"table_id": "t_nope"}),
                 404, "not_found")


def test_patch_onto_a_taken_table_is_409(world, book):
    assert_status(book(table_id="t_3", at="19:00"), 201)
    ref = book(table_id="t_2", at="19:00").json()["reference"]
    assert_error(world.ada.patch(f"/reservations/{ref}", json={"table_id": "t_3"}),
                 409, "table_unavailable")


def test_patch_a_cancelled_reservation_is_409(world, book):
    ref = book(at="19:00").json()["reference"]
    assert_status(world.ada.post(f"/reservations/{ref}/cancel"), 200)
    assert_error(world.ada.patch(f"/reservations/{ref}", json={"party_size": 2}),
                 409, "reservation_cancelled")


def test_patch_someone_elses_reservation_is_404(world, book):
    ref = book(world.ada, at="19:00").json()["reference"]
    assert_error(world.bob.patch(f"/reservations/{ref}", json={"party_size": 2}),
                 404, "not_found")
