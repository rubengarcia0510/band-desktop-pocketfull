"""The small API contract: health, reset, read, increment, shared state."""
import pytest

from harness.http import assert_status

pytestmark = pytest.mark.stage(1)


def value(response):
    assert_status(response, 200)
    assert response.headers["content-type"].split(";")[0].strip() == "application/json"
    body = response.json()
    assert type(body["value"]) is int, f"value must be an integer: {body}"
    return body["value"]


def test_health(anon):
    response = assert_status(anon.get("/health"), 200)
    assert response.json() == {"status": "ok"}


def test_reset_returns_no_content_without_authentication(reset):
    assert reset({"value": 0}).content == b""


@pytest.mark.parametrize("seed", [0, 7])
def test_reset_loads_value(reset, anon, seed):
    reset({"value": seed})
    assert value(anon.get("/counter")) == seed


def test_increment_returns_new_value(reset, anon):
    reset({"value": 7})
    assert value(anon.post("/counter/increment")) == 8
    assert value(anon.post("/counter/increment", json={})) == 9
    assert value(anon.get("/counter")) == 9


def test_clients_share_one_counter(reset, api):
    reset({"value": 0})
    first, second = api(), api()
    assert value(first.post("/counter/increment")) == 1
    assert value(second.get("/counter")) == 1
    assert value(second.post("/counter/increment")) == 2
    assert value(first.get("/counter")) == 2


def test_reads_do_not_change_value(reset, anon):
    reset({"value": 12})
    for _ in range(3):
        assert value(anon.get("/counter")) == 12


def test_reset_replaces_previous_state(reset, anon):
    reset({"value": 100})
    assert value(anon.post("/counter/increment")) == 101
    reset({"value": 0})
    assert value(anon.get("/counter")) == 0
    assert value(anon.post("/counter/increment")) == 1
