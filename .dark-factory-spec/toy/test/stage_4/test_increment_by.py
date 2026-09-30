"""`by` adds a chosen amount, and everything stages 1-3 checked still holds."""
import pytest

from harness.concurrent import burst, no_5xx, tally
from harness.http import assert_status

pytestmark = pytest.mark.stage(4)


def value(response):
    assert_status(response, 200)
    body = response.json()
    assert type(body["value"]) is int, f"value must be an integer: {body}"
    return body["value"]


def test_by_adds_that_amount(reset, anon):
    reset({"value": 7})
    assert value(anon.post("/counter/increment", json={"by": 5})) == 12
    assert value(anon.post("/counter/increment", json={"by": 1})) == 13
    assert value(anon.get("/counter")) == 13


def test_increment_without_by_still_adds_one(reset, anon):
    reset({"value": 7})
    assert value(anon.post("/counter/increment")) == 8
    assert value(anon.post("/counter/increment", json={})) == 9


@pytest.mark.parametrize("by", [0, -1, -20, "5", 1.5])
def test_a_by_that_is_not_an_integer_of_one_or_more_is_rejected(reset, anon, by):
    reset({"value": 7})
    assert_status(anon.post("/counter/increment", json={"by": by}), 400)
    assert value(anon.get("/counter")) == 7, "a rejected increment must change nothing"


def test_a_rejected_increment_does_not_stop_the_next_one(reset, anon):
    reset({"value": 0})
    assert_status(anon.post("/counter/increment", json={"by": 0}), 400)
    assert value(anon.post("/counter/increment", json={"by": 3})) == 3


@pytest.mark.parametrize("seed", [0, 37])
def test_no_lost_amounts(reset, api, seed):
    """Twenty clients adding different amounts: 1+2+...+20 = 210, none lost."""
    reset({"value": seed})
    clients = [api() for _ in range(20)]
    out = burst(lambda i: clients[i].post("/counter/increment", json={"by": i + 1}), 20)
    no_5xx(out)
    assert tally(out) == {200: 20}, f"every increment must succeed: {tally(out)}"
    values = [response.json()["value"] for response in out]
    assert len(set(values)) == 20, f"no two increments may return the same value: {values}"
    assert max(values) == seed + 210, f"the last increment must see every earlier one: {values}"
    assert assert_status(clients[0].get("/counter"), 200).json()["value"] == seed + 210, \
        "an amount was lost"
