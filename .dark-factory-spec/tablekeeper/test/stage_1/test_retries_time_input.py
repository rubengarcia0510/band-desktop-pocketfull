"""Stage 1 — idempotent replay (§7), the DST rules (§8) and the validation rule (§5)."""
import pytest

import fixtures as fx
from harness.http import assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(1)

# The transitions the harness uses, from §9. Dates in the past are legal: the spec
# forbids rejecting a booking for being in the past.
BERLIN_SPRING, BERLIN_FALL = "2026-03-29", "2026-10-25"
NY_SPRING, NY_FALL = "2026-03-08", "2026-11-01"


@pytest.fixture
def ada(reset, api):
    reset(fx.fixture())
    return api().authenticate(fx.ADA["email"], fx.ADA["password"])


def _book(client, date, at="19:00", **over):
    body = {"restaurant_id": "r_anker", "table_id": "t_2",
            "starts_at_local": fx.local(date, at), "party_size": 4}
    body.update(over)
    return client.post("/reservations", json=body,
                       idempotency_key=over.pop("key", None) or new_key())


# ---- retries -------------------------------------------------------------

def test_replay_after_cancel_returns_the_original_confirmed_body(ada):
    date = fx.booking_date()
    key = new_key()
    first = assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": fx.local(date, "19:00"), "party_size": 4},
        idempotency_key=key), 201).json()
    assert_status(ada.post(f"/reservations/{first['reference']}/cancel"), 200)
    replay = assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": fx.local(date, "19:00"), "party_size": 4},
        idempotency_key=key), 200).json()
    assert replay == first
    assert replay["status"] == "confirmed"


def test_same_key_changed_party_size_is_reuse(ada):
    date = fx.booking_date()
    key = new_key()
    body = {"restaurant_id": "r_anker", "table_id": "t_2",
            "starts_at_local": fx.local(date, "19:00"), "party_size": 4}
    assert_status(ada.post("/reservations", json=body, idempotency_key=key), 201)
    assert_error(ada.post("/reservations", json={**body, "party_size": 3},
                          idempotency_key=key), 409, "idempotency_key_reuse")


def test_same_key_from_another_account_books_normally(reset, api, base_url):
    reset(fx.fixture())
    date = fx.booking_date()
    key = "a-shared-key"
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    bob = api().authenticate(fx.BOB["email"], fx.BOB["password"])
    assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": fx.local(date, "19:00"), "party_size": 4},
        idempotency_key=key), 201)
    assert_status(bob.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_3",
        "starts_at_local": fx.local(date, "19:00"), "party_size": 4},
        idempotency_key=key), 201)


# ---- time ----------------------------------------------------------------

@pytest.fixture
def zoned(reset, api):
    """Berlin and New York restaurants, open around the clock so slots exist."""
    def _make():
        berlin = fx.restaurant("r_berlin", timezone="Europe/Berlin",
                               opening_hours=fx.all_week("00:00", "23:30"))
        newyork = fx.restaurant("r_ny", timezone="America/New_York",
                                opening_hours=fx.all_week("00:00", "23:30"))
        reset(fx.fixture(restaurants=[berlin, newyork]))
        return api().authenticate(fx.ADA["email"], fx.ADA["password"])
    return _make


def _slots(client, rid, date):
    resp = client.get("/availability", params={
        "restaurant_id": rid, "date": date, "party_size": 4})
    assert_status(resp, 200)
    return [s["starts_at_local"].split("T")[1] for s in resp.json()["slots"]]


def test_booking_a_skipped_local_time_is_rejected(zoned):
    ada = zoned()
    resp = ada.post("/reservations", json={
        "restaurant_id": "r_berlin", "table_id": "t_2",
        "starts_at_local": f"{BERLIN_SPRING}T02:30", "party_size": 4},
        idempotency_key=new_key())
    assert_error(resp, 422, "invalid_local_time")


def test_fall_back_repeated_hour_appears_once(zoned, anon):
    zoned()
    times = _slots(anon, "r_berlin", BERLIN_FALL)
    assert times.count("02:00") == 1, f"the repeated hour appears once: {times}"
    assert times.count("02:30") == 1


def test_fall_back_resolves_to_the_first_occurrence(zoned):
    """02:00 on a fall-back night is the one before the clocks change: +02:00."""
    ada = zoned()
    body = assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_berlin", "table_id": "t_2",
        "starts_at_local": f"{BERLIN_FALL}T02:00", "party_size": 4},
        idempotency_key=new_key()), 201).json()
    assert body["starts_at"].endswith("+02:00"), \
        f"first occurrence is CEST (+02:00), got {body['starts_at']}"


def test_duration_is_absolute_time_not_wall_clock(zoned):
    """90 minutes from 01:30 on a fall-back night ends at local 02:00, not 03:00."""
    ada = zoned()
    body = assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_berlin", "table_id": "t_2",
        "starts_at_local": f"{BERLIN_FALL}T01:30", "party_size": 4},
        idempotency_key=new_key()), 201).json()
    assert "T02:00" in body["ends_at"], \
        f"90 real minutes from 01:30 ends at local 02:00, got {body['ends_at']}"


def test_two_zones_book_the_same_instant_from_different_local_times(zoned):
    """Berlin 18:00 CET and New York 12:00 EST are the same absolute moment."""
    ada = zoned()
    from datetime import datetime
    made = {}
    for rid, at in (("r_berlin", "18:00"), ("r_ny", "12:00")):
        body = assert_status(ada.post("/reservations", json={
            "restaurant_id": rid, "table_id": "t_2",
            "starts_at_local": f"2026-12-01T{at}", "party_size": 4},
            idempotency_key=new_key()), 201).json()
        made[rid] = datetime.fromisoformat(body["starts_at"])
    assert made["r_berlin"] == made["r_ny"], (
        f"same instant expected: {made}")


def test_offsets_are_correct_on_both_sides_of_a_transition(zoned):
    ada = zoned()
    before = assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_berlin", "table_id": "t_2",
        "starts_at_local": f"{BERLIN_FALL}T01:00", "party_size": 4},
        idempotency_key=new_key()), 201).json()
    after = assert_status(ada.post("/reservations", json={
        "restaurant_id": "r_berlin", "table_id": "t_3",
        "starts_at_local": f"{BERLIN_FALL}T12:00", "party_size": 4},
        idempotency_key=new_key()), 201).json()
    assert before["starts_at"].endswith("+02:00"), before["starts_at"]
    assert after["starts_at"].endswith("+01:00"), after["starts_at"]


# ---- awkward input -------------------------------------------------------


@pytest.mark.parametrize("value", [
    "2026-09-24T19:00:00+02:00", "2026-09-24T19:00Z", "2026-09-24T19:00:00",
])
def test_starts_at_local_must_carry_no_offset_or_seconds(ada, value):
    assert_error(_book(ada, fx.booking_date(), starts_at_local=value),
                 422, "validation_failed")


@pytest.mark.parametrize("party", [0, -1, "4", 1.5])
def test_bad_party_sizes_never_500(ada, party):
    resp = _book(ada, fx.booking_date(), party_size=party)
    assert resp.status_code == 422, f"expected 422, got {resp.status_code}"
    assert resp.json()["error"]["code"] == "validation_failed"


def test_unknown_reference_is_404(ada):
    assert_error(ada.get("/reservations/NOPE12"), 404, "not_found")


def test_someone_elses_reference_is_404(reset, api):
    reset(fx.fixture())
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    bob = api().authenticate(fx.BOB["email"], fx.BOB["password"])
    ref = _book(ada, fx.booking_date()).json()["reference"]
    assert_error(bob.get(f"/reservations/{ref}"), 404, "not_found")
    assert_error(bob.post(f"/reservations/{ref}/cancel"), 404, "not_found")


def test_table_from_another_restaurant_is_404(reset, api):
    other = fx.restaurant("r_other", tables=[{"id": "t_x", "label": "X", "capacity": 4}])
    reset(fx.fixture(restaurants=[fx.restaurant(), other]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    assert_error(_book(ada, fx.booking_date(), table_id="t_x"), 404, "not_found")


def test_impossible_date_is_422(anon, ada):
    assert_error(anon.get("/availability", params={
        "restaurant_id": "r_anker", "date": "2026-02-30", "party_size": 4}),
        422, "validation_failed")
