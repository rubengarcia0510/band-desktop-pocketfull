"""Twenty simultaneous increments must each take effect exactly once."""
import pytest

from harness.concurrent import burst, no_5xx, tally
from harness.http import assert_status

pytestmark = pytest.mark.stage(3)


@pytest.mark.parametrize("seed", [0, 37])
def test_no_lost_increments(reset, api, seed):
    reset({"value": seed})
    clients = [api() for _ in range(20)]
    current = seed
    for _ in range(3):
        out = burst(lambda i: clients[i].post("/counter/increment"), len(clients))
        no_5xx(out)
        assert tally(out) == {200: 20}, f"every increment must succeed: {tally(out)}"
        values = [response.json()["value"] for response in out]
        assert all(type(v) is int for v in values), f"noninteger values: {values}"
        assert sorted(values) == list(range(current + 1, current + 21)), \
            f"each increment must return a distinct successive value: {values}"
        current += 20
        assert assert_status(clients[0].get("/counter"), 200).json()["value"] == current, \
            "an increment was lost"
