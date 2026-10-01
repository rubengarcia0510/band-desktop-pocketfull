"""One page backed by the shared counter, located by exact data-testid values."""
import pytest
from playwright.sync_api import expect

from harness.http import assert_status

pytestmark = pytest.mark.stage(2)


def test_page_displays_seeded_value(reset, page):
    reset({"value": 7})
    page.goto("/")
    expect(page.get_by_test_id("counter-value")).to_have_text("7")
    expect(page.get_by_test_id("increment-button")).to_be_visible()


def test_button_increments_server_value(reset, page, anon):
    reset({"value": 7})
    page.goto("/")
    expect(page.get_by_test_id("counter-value")).to_have_text("7")
    page.get_by_test_id("increment-button").click()
    expect(page.get_by_test_id("counter-value")).to_have_text("8")
    assert assert_status(anon.get("/counter"), 200).json()["value"] == 8


def test_value_survives_page_reload(reset, page):
    reset({"value": 0})
    page.goto("/")
    for expected in range(1, 4):
        page.get_by_test_id("increment-button").click()
        expect(page.get_by_test_id("counter-value")).to_have_text(str(expected))
    page.reload()
    expect(page.get_by_test_id("counter-value")).to_have_text("3")


def test_reload_reads_changes_from_another_client(reset, page, anon):
    reset({"value": 12})
    page.goto("/")
    expect(page.get_by_test_id("counter-value")).to_have_text("12")
    assert_status(anon.post("/counter/increment"), 200)
    page.reload()
    expect(page.get_by_test_id("counter-value")).to_have_text("13")
