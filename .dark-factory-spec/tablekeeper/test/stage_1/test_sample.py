"""Stage 1 sample — the shipped smoke checks.

This is a sample, not the graded suite. It shows the shape of each endpoint once so a
service can be wired up against it; the checks that decide the result are the spec's,
and the spec is the contract. Passing every check here means the wiring is right, not
that stage 1 holds.
"""
import re

import httpx
import pytest

import fixtures as fx
from harness.concurrent import burst, no_5xx, tally
from harness.http import Api, assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(1)

REFERENCE = re.compile(r"^[A-Z0-9]{6,12}$")


def _availability(client, rid, date, party_size):
    return client.get("/availability", params={
        "restaurant_id": rid, "date": date, "party_size": party_size})


def test_health_reports_ok(base_url):
    resp = httpx.get(f"{base_url}/health", timeout=5)
    assert_status(resp, 200)
    assert resp.json()["status"] == "ok"


def test_reset_is_synchronous_and_replaces_all_state(reset, anon):
    """When reset returns 204 the next request sees the fixture and nothing else."""
    reset(fx.fixture(restaurants=[fx.restaurant("r_one", name="One")]))
    assert [r["id"] for r in anon.get("/restaurants").json()["restaurants"]] == ["r_one"]

    reset(fx.fixture(restaurants=[fx.restaurant("r_two", name="Two")]))
    assert [r["id"] for r in anon.get("/restaurants").json()["restaurants"]] == ["r_two"]


def test_signup_returns_a_usable_token(world, api):
    resp = world.ada.signup("new@example.com", "correct horse", "New")
    assert_status(resp, 201)
    body = resp.json()
    assert body["display_name"] == "New" and body["token"]
    assert_status(api(body["token"]).get("/reservations"), 200)


def test_login_returns_a_usable_token(world, api):
    resp = world.ada.login(fx.ADA["email"], fx.ADA["password"])
    assert_status(resp, 200)
    assert_status(api(resp.json()["token"]).get("/reservations"), 200)


@pytest.mark.parametrize("path", ["/restaurants", "/availability"])
def test_public_endpoints_need_no_token(world, anon, path):
    """Diners browse before they sign in, so these three are public (§8)."""
    params = {"restaurant_id": world.rid, "date": world.date, "party_size": 2}
    resp = anon.get(path, params=params if path == "/availability" else None)
    assert resp.status_code == 200, f"{path} must be public, got {resp.status_code}"


def test_restaurant_list_shape(world, anon):
    body = assert_status(anon.get("/restaurants"), 200).json()
    entry = next(r for r in body["restaurants"] if r["id"] == world.rid)
    assert entry["name"] == world.restaurant["name"]
    assert entry["timezone"] == world.timezone


def test_availability_slot_grid(world, anon):
    """A slot appears for every step from `opens` while slot + duration <= closes."""
    body = assert_status(_availability(anon, world.rid, world.date, 2), 200).json()
    assert body["restaurant_id"] == world.rid
    assert body["date"] == world.date
    assert body["timezone"] == world.timezone
    times = [s["starts_at_local"].split("T")[1] for s in body["slots"]]
    assert times == fx.expected_slots()


def test_available_tables_filter_by_capacity_in_fixture_order(world, anon):
    """Only tables with capacity >= party_size, in fixture order."""
    slots = _availability(anon, world.rid, world.date, 4).json()["slots"]
    assert slots[0]["available_table_ids"] == ["t_2", "t_3"]
    slots = _availability(anon, world.rid, world.date, 6).json()["slots"]
    assert slots[0]["available_table_ids"] == ["t_3"]


def test_create_returns_the_documented_shape(world, book):
    body = assert_status(book(table_id="t_2", at="19:00", party_size=4), 201).json()
    assert body["restaurant_id"] == world.rid
    assert body["table_id"] == "t_2"
    assert body["party_size"] == 4
    assert body["status"] == "confirmed"
    assert body["starts_at_local"] == fx.local(world.date, "19:00")
    assert body["reservation_id"] and body["created_at"]
    assert REFERENCE.match(body["reference"]), body["reference"]


def test_ends_at_is_start_plus_duration(world, book):
    body = book(at="19:00").json()
    assert body["starts_at"].startswith(f"{world.date}T19:00:00")
    assert body["ends_at"].startswith(f"{world.date}T20:30:00")


def test_double_booking_the_same_table_is_409(world, book):
    assert_status(book(table_id="t_2", at="19:00"), 201)
    assert_error(book(table_id="t_2", at="19:00"), 409, "table_unavailable")


def test_read_by_reference(world, book):
    ref = book(at="19:00").json()["reference"]
    assert world.ada.get(f"/reservations/{ref}").json()["reference"] == ref


def test_cancel_sets_status_and_frees_the_table(world, book, anon):
    ref = book(table_id="t_2", at="19:00").json()["reference"]
    body = assert_status(world.ada.post(f"/reservations/{ref}/cancel"), 200).json()
    assert body["status"] == "cancelled"
    slots = anon.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": 4}).json()["slots"]
    slot = next(s for s in slots if s["starts_at_local"].endswith("19:00"))
    assert "t_2" in slot["available_table_ids"], "cancel must free the table immediately"


def test_patch_changes_the_table_and_frees_the_old_one(world, book, anon):
    ref = book(table_id="t_2", at="19:00").json()["reference"]
    body = assert_status(
        world.ada.patch(f"/reservations/{ref}", json={"table_id": "t_3"}), 200).json()
    assert body["table_id"] == "t_3"
    slots = anon.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": 4}).json()["slots"]
    slot = next(s for s in slots if s["starts_at_local"].endswith("19:00"))
    assert "t_2" in slot["available_table_ids"]
    assert "t_3" not in slot["available_table_ids"]


def test_first_use_is_201_replay_is_200_with_the_same_body(world, book):
    key = new_key()
    first = assert_status(book(key=key, table_id="t_2", at="19:00"), 201).json()
    replay = assert_status(book(key=key, table_id="t_2", at="19:00"), 200).json()
    assert replay == first, "a replay returns the original response verbatim"


def test_missing_key_is_400(world):
    resp = world.ada.post("/reservations", json={
        "restaurant_id": world.rid, "table_id": "t_2",
        "starts_at_local": fx.local(world.date, "19:00"), "party_size": 4})
    assert_error(resp, 400, "missing_idempotency_key")


# ---- under load ------------------------------------------------------------

def test_one_slot_under_ten_clients(reset, base_url):
    """Ten accounts race for one table and one slot: exactly one 201.

    The shape once. The graded run uses the §2 budget of 50 in flight, and asks the
    same of cancel-and-rebook, of a PATCH onto one free table, and of a key replayed
    by twenty clients at once.
    """
    users = [dict(fx.ADA, id=f"u_{i}", email=f"r{i}@example.com") for i in range(10)]
    reset(fx.fixture(users=users))
    date = fx.booking_date()
    crowd = [Api(base_url).authenticate(u["email"], u["password"]) for u in users]
    body = {"restaurant_id": "r_anker", "table_id": "t_2",
            "starts_at_local": fx.local(date, "19:00"), "party_size": 4}
    try:
        out = burst(lambda i: crowd[i].post(
            "/reservations", json=body, idempotency_key=new_key()), 10)
    finally:
        for client in crowd:
            client.close()
    no_5xx(out)
    counts = tally(out)
    assert counts.get(201) == 1, f"exactly one booking may win: {counts}"
    assert counts.get(409) == 9, f"the other nine must be 409: {counts}"


def test_export_can_restore_a_booking(world, book, reset):
    receipt = book().json()
    snapshot = world.ada.get('/_test/export')
    assert snapshot.status_code == 200
    reset(world.fixture)
    restored = world.ada.post('/_test/import', json=snapshot.json())
    assert restored.status_code == 204
    assert world.ada.get('/reservations/' + receipt['reference']).json() == receipt


def test_a_move_batch_of_one_moves_the_booking(world, book):
    booking = assert_status(book(table_id='t_1', party_size=2), 201).json()
    body = {'moves': [dict(reference=booking['reference'], table_id='t_2')]}
    result = assert_status(world.ada.post('/reservation-moves', json=body,
                           idempotency_key=new_key()), 201).json()
    assert [r['table_id'] for r in result['reservations']] == ['t_2']
