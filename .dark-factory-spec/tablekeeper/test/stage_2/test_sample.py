"""Stage 2 sample — the shipped smoke checks.

This is a sample, not the graded suite. It shows the shape of each surface once so a
service can be wired up against it; the spec is the contract and the graded checks are
the spec's. Passing everything here means the wiring is right, not that the stage holds.
"""
import re

import pytest

import fixtures as fx

pytestmark = pytest.mark.stage(2)


@pytest.fixture
def seeded(reset):
    fixture = fx.fixture()
    reset(fixture)
    return fixture


def sel(name: str) -> str:
    return f"[data-testid='{name}']"


def log_in(page, email=None, password="correct horse", expect_success=True):
    page.goto("/login")
    page.fill(sel("login-email"), email or fx.ADA["email"])
    page.fill(sel("login-password"), password)
    page.click(sel("login-submit"))
    if expect_success:
        page.wait_for_selector(sel("current-user"))


def search(page, date=None, party_size=4, restaurant="r_anker"):
    page.goto("/")
    page.select_option(sel("restaurant-select"), restaurant)
    page.fill(sel("date-input"), date or fx.booking_date())
    page.fill(sel("party-size-input"), str(party_size))
    page.click(sel("search-button"))
    page.wait_for_selector(f"{sel('availability-grid')}, {sel('no-slots')}")


@pytest.mark.parametrize("route,anchor", [
    ("/", "search-button"), ("/signup", "signup-submit"),
    ("/login", "login-submit"), ("/lookup", "lookup-submit"),
])
def test_routes_are_directly_navigable(seeded, page, route, anchor):
    page.goto(route)
    page.wait_for_selector(sel(anchor), state="attached")


def test_login_signs_you_in_and_logout_signs_you_out(seeded, page):
    log_in(page)
    page.wait_for_selector(sel("current-user"))
    assert fx.ADA["display_name"] in page.text_content(sel("current-user"))
    page.click(sel("logout-button"))
    page.wait_for_selector(sel("current-user"), state="detached")


def test_booking_flow_reaches_a_confirmation(seeded, page):
    log_in(page)
    search(page, party_size=4)
    page.click(sel("slot-t_2-19:00"))
    page.wait_for_selector(sel("booking-form"))

    summary = page.text_content(sel("booking-summary"))
    assert "19:00" in summary, f"summary must carry the local start time: {summary!r}"
    assert "2" in summary, f"summary must carry the table label: {summary!r}"
    assert page.input_value(sel("booking-party-size")) == "4", \
        "party size is pre-filled from the search"

    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    reference = page.text_content(sel("confirmation-reference")).strip()
    assert re.fullmatch(r"[A-Z0-9]{6,12}", reference), \
        f"confirmation-reference must be exactly the reference: {reference!r}"
    details = page.text_content(sel("confirmation-details"))
    for expected in ("Zum Anker", "2", "19:00"):
        assert expected in details, f"{expected!r} missing from {details!r}"


def test_preceding_stage_accounts_survive_import(previous_api, api):
    import fixtures as fx
    assert previous_api.post('/_test/reset', json=fx.fixture()).status_code == 204
    previous_api.authenticate(fx.ADA['email'], fx.ADA['password'])
    snapshot = previous_api.get('/_test/export')
    assert snapshot.status_code == 200
    target = api(token=previous_api.token)
    assert target.post('/_test/import', json=snapshot.json()).status_code == 204
    assert target.get('/reservations').status_code == 200


def test_a_combination_occupies_both_tables(reset, api):
    from harness.http import new_key
    restaurant = fx.restaurant()
    restaurant['combinable'] = [['t_1', 't_2']]
    reset(fx.fixture(restaurants=[restaurant]))
    ada = api().authenticate(fx.ADA['email'], fx.ADA['password'])
    result = ada.post('/reservations', json=dict(restaurant_id='r_anker',
        table_ids=['t_1', 't_2'], party_size=6, starts_at_local=fx.local(fx.booking_date())),
        idempotency_key=new_key())
    assert result.status_code == 201
    assert result.json()['table_ids'] == ['t_1', 't_2']
