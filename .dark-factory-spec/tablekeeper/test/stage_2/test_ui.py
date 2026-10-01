"""Stage 2 — the UI over the stage-1 API (§9).

Every element is found by its exact `data-testid` and by nothing else.
"""
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


def sign_up(page, email="new@example.com", password="correct horse", name="New"):
    page.goto("/signup")
    page.fill(sel("signup-email"), email)
    page.fill(sel("signup-password"), password)
    page.fill(sel("signup-display-name"), name)
    page.click(sel("signup-submit"))
    page.wait_for_selector(sel("current-user"))


def log_in(page, email=None, password="correct horse", expect_success=True):
    page.goto("/login")
    page.fill(sel("login-email"), email or fx.ADA["email"])
    page.fill(sel("login-password"), password)
    page.click(sel("login-submit"))
    if expect_success:
        # Wait for the session to exist before navigating away, or the next
        # goto races the in-flight login and the token is never stored.
        page.wait_for_selector(sel("current-user"))


def search(page, date=None, party_size=4, restaurant="r_anker"):
    page.goto("/")
    page.select_option(sel("restaurant-select"), restaurant)
    page.fill(sel("date-input"), date or fx.booking_date())
    page.fill(sel("party-size-input"), str(party_size))
    page.click(sel("search-button"))
    page.wait_for_selector(f"{sel('availability-grid')}, {sel('no-slots')}")


# ---- routes and auth -----------------------------------------------------


def test_signup_signs_you_in(seeded, page):
    sign_up(page, name="Dee")
    page.wait_for_selector(sel("current-user"))
    assert "Dee" in page.text_content(sel("current-user"))


def test_bad_login_shows_auth_error(seeded, page):
    log_in(page, password="wrong password", expect_success=False)
    page.wait_for_selector(sel("auth-error"))
    assert page.text_content(sel("auth-error")).strip()


def test_auth_error_is_absent_when_there_is_none(seeded, page):
    page.goto("/login")
    assert page.query_selector(sel("auth-error")) is None, \
        "auth-error is present only when there is an error"


# ---- availability grid ---------------------------------------------------

def test_grid_shows_a_cell_per_table_per_slot(seeded, page):
    search(page, party_size=2)
    for at in fx.expected_slots():
        for table in ("t_1", "t_2", "t_3"):
            assert page.query_selector(sel(f"slot-{table}-{at}")) is not None, \
                f"missing cell slot-{table}-{at}"


def test_cells_carry_data_available(seeded, page):
    search(page, party_size=6)
    # t_1 holds 2 and t_2 holds 4, so neither can seat a party of 6.
    assert page.get_attribute(sel("slot-t_1-19:00"), "data-available") == "false"
    assert page.get_attribute(sel("slot-t_3-19:00"), "data-available") == "true"


def test_closed_day_shows_no_slots(reset, page):
    date = fx.booking_date()
    closed = [h for h in fx.all_week() if h["weekday"] != fx.weekday_of(date)]
    reset(fx.fixture(restaurants=[fx.restaurant(opening_hours=closed)]))
    search(page, date=date)
    page.wait_for_selector(sel("no-slots"))


def test_clicking_an_unavailable_cell_does_nothing(seeded, page):
    log_in(page)
    search(page, party_size=6)
    # force: a disabled cell also does nothing, and Playwright would wait for it to enable.
    page.click(sel("slot-t_1-19:00"), force=True)
    assert page.query_selector(sel("booking-form")) is None, \
        "an unavailable cell must not open the booking form"


def test_booking_while_signed_out_shows_auth_error_or_goes_to_login(seeded, page):
    search(page, party_size=4)
    page.click(sel("slot-t_2-19:00"))
    page.wait_for_selector(f"{sel('auth-error')}, {sel('login-submit')}")


# ---- booking -------------------------------------------------------------


def test_a_booked_slot_is_unavailable_on_the_next_search(seeded, page):
    log_in(page)
    search(page, party_size=4)
    page.click(sel("slot-t_2-19:00"))
    page.wait_for_selector(sel("booking-form"))
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))

    search(page, party_size=4)
    assert page.get_attribute(sel("slot-t_2-19:00"), "data-available") == "false"


def test_booking_error_is_shown_when_the_booking_fails(seeded, page, api):
    """Take the table over the API between opening the form and submitting."""
    log_in(page)
    search(page, party_size=4)
    page.click(sel("slot-t_2-19:00"))
    page.wait_for_selector(sel("booking-form"))

    from harness.http import new_key
    thief = api().authenticate(fx.BOB["email"], fx.BOB["password"])
    taken = thief.post("/reservations", json={
        "restaurant_id": "r_anker", "table_id": "t_2",
        "starts_at_local": fx.local(fx.booking_date(), "19:00"), "party_size": 4},
        idempotency_key=new_key())
    assert taken.status_code == 201, taken.text

    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("booking-error"))
    assert page.query_selector(sel("confirmation")) is None


# ---- lookup --------------------------------------------------------------

def _book_via_ui(page) -> str:
    log_in(page)
    search(page, party_size=4)
    page.click(sel("slot-t_2-19:00"))
    page.wait_for_selector(sel("booking-form"))
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    return page.text_content(sel("confirmation-reference")).strip()


def test_lookup_shows_the_reservation(seeded, page):
    reference = _book_via_ui(page)
    page.goto("/lookup")
    page.fill(sel("lookup-reference-input"), reference)
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-detail"))
    assert page.text_content(sel("reservation-status")).strip() == "confirmed"


def test_cancel_from_lookup_updates_without_a_manual_reload(seeded, page):
    reference = _book_via_ui(page)
    page.goto("/lookup")
    page.fill(sel("lookup-reference-input"), reference)
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-cancel-button"))
    page.click(sel("reservation-cancel-button"))
    page.wait_for_selector(sel("reservation-cancel-button"), state="detached")
    assert page.text_content(sel("reservation-status")).strip() == "cancelled"


def test_cancelling_frees_the_slot(seeded, page):
    reference = _book_via_ui(page)
    page.goto("/lookup")
    page.fill(sel("lookup-reference-input"), reference)
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-cancel-button"))
    page.click(sel("reservation-cancel-button"))
    page.wait_for_selector(sel("reservation-cancel-button"), state="detached")
    search(page, party_size=4)
    assert page.get_attribute(sel("slot-t_2-19:00"), "data-available") == "true"


def test_unknown_reference_shows_reservation_error(seeded, page):
    log_in(page)
    page.goto("/lookup")
    page.fill(sel("lookup-reference-input"), "ZZZZZZ")
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-error"))
    assert page.query_selector(sel("reservation-detail")) is None


# ---- a double submit is a replay ------------------------------------------

def _open_booking_form(page, party_size=4):
    log_in(page)
    search(page, party_size=party_size)
    page.click(sel("slot-t_2-19:00"))
    page.wait_for_selector(sel("booking-form"))


def test_submitting_the_booking_form_twice_books_once(seeded, page):
    """The form stays on screen, so a second press sends the same body. A form
    that mints its idempotency key at submit time sends a new one and is answered
    409 table_unavailable."""
    _open_booking_form(page)
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    first = page.text_content(sel("confirmation-reference")).strip()

    page.click(sel("booking-submit"))
    page.wait_for_timeout(500)
    assert page.query_selector(sel("booking-error")) is None, \
        "the second submit was refused instead of replayed"
    assert page.text_content(sel("confirmation-reference")).strip() == first


def test_a_double_submit_leaves_one_reservation(seeded, page, api):
    _open_booking_form(page)
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    page.click(sel("booking-submit"))
    page.wait_for_timeout(500)

    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    confirmed = [r for r in ada.get("/reservations").json()["reservations"]
                 if r["status"] == "confirmed"]
    assert len(confirmed) == 1, f"booked {len(confirmed)} times"


def test_changing_the_form_first_is_a_different_booking(seeded, page, api):
    """Editing a field starts a new booking, so it must not replay the old one."""
    _open_booking_form(page)
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    page.fill(sel("booking-party-size"), "2")
    page.click(sel("booking-submit"))
    page.wait_for_timeout(500)
    assert page.query_selector(sel("booking-error")) is not None, \
        "the slot is taken, so a genuinely new booking of it must be refused"
