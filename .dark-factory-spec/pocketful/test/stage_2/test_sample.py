"""Stage 2 sample — the shipped smoke checks.

This is a sample, not the graded suite. It shows the shape of each surface once so a
service can be wired up against it; the spec is the contract and the graded checks are
the spec's. Passing everything here means the wiring is right, not that the stage holds.
"""
import pytest

import fixtures as fx
from playwright.sync_api import expect
from harness.http import assert_status, new_key

pytestmark = pytest.mark.stage(2)


def sel(name: str) -> str:
    return f"[data-testid='{name}']"


def money(minor: int, minor_units: int = 2, currency: str = "EUR") -> str:
    """`100.00 EUR`; with minor_units 0 there is no decimal point at all."""
    if minor_units == 0:
        return f"{minor} {currency}"
    text = str(minor).rjust(minor_units + 1, "0")
    return f"{text[:-minor_units]}.{text[-minor_units:]} {currency}"


@pytest.fixture
def seeded(reset):
    fixture = fx.fixture()
    reset(fixture)
    return fixture


def log_in(page, email=None, password="correct horse", expect_success=True):
    page.goto("/login")
    page.fill(sel("login-email"), email or fx.ADA["email"])
    page.fill(sel("login-password"), password)
    page.click(sel("login-submit"))
    if expect_success:
        page.wait_for_selector(sel("current-user"))


def _pay(page, handle="bob", amount="15.00", note="", visibility=None):
    page.goto("/")
    page.wait_for_selector(sel("pay-submit"))
    page.fill(sel("pay-handle"), handle)
    page.fill(sel("pay-amount"), amount)
    if note:
        page.fill(sel("pay-note"), note)
    if visibility:
        page.select_option(sel("pay-visibility"), visibility)
    page.click(sel("pay-submit"))


@pytest.mark.parametrize("route,anchor", [
    ("/", "pay-submit"), ("/requests", "incoming-list"), ("/split", "split-submit"),
    ("/signup", "signup-submit"), ("/login", "login-submit"),
])
def test_routes_are_directly_navigable(seeded, page, route, anchor):
    log_in(page)
    page.goto(route)
    page.wait_for_selector(sel(anchor), state="attached")


def test_balance_is_formatted_and_carries_minor_units(seeded, page):
    log_in(page)
    page.goto("/")
    page.wait_for_selector(sel("wallet-balance"))
    assert page.text_content(sel("wallet-balance")).strip() == money(fx.ADA["balance"])
    assert page.get_attribute(sel("wallet-balance"), "data-amount") == str(fx.ADA["balance"])


def test_refresh_observes_another_clients_payment(seeded, page, api):
    log_in(page)
    page.goto('/')
    expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount', '10000')
    ada = api().authenticate(fx.ADA['email'], fx.ADA['password'])
    payment = assert_status(ada.post('/payments', json={'to_handle': 'bob', 'amount': 300},
                                     idempotency_key=new_key()), 201).json()
    page.click(sel('wallet-refresh'))
    expect(page.get_by_test_id('wallet-balance')).to_have_attribute('data-amount', '9700')
    expect(page.get_by_test_id('activity-item-' + payment['payment_id'])).to_be_visible()


def test_paying_updates_the_balance_without_a_manual_reload(seeded, page):
    log_in(page)
    _pay(page, amount="15.00")
    page.wait_for_selector(f"{sel('wallet-balance')}[data-amount='{10_000 - 1500}']")
    assert page.text_content(sel("wallet-balance")).strip() == money(8500)


def test_preceding_stage_accounts_survive_import(previous_api, api):
    import fixtures as fx
    assert previous_api.post('/_test/reset', json=fx.fixture()).status_code == 204
    previous_api.authenticate(fx.ADA['email'], fx.ADA['password'])
    snapshot = previous_api.get('/_test/export')
    assert snapshot.status_code == 200
    target = api(token=previous_api.token)
    assert target.post('/_test/import', json=snapshot.json()).status_code == 204
    assert target.get('/me').json()['balance'] == 10000


def test_a_hold_reserves_funds_without_moving_them(reset, api):
    reset(fx.fixture())
    ada = api().authenticate(fx.ADA['email'], fx.ADA['password'])
    held = assert_status(ada.post('/authorizations', json={'to_handle': 'bob', 'amount': 2000},
                                  idempotency_key=new_key()), 201).json()
    assert held['status'] == 'open'
    me = assert_status(ada.get('/me'), 200).json()
    assert me['total'] == fx.ADA['balance']
    assert me['held'] == 2000 and me['available'] == me['total'] - 2000
