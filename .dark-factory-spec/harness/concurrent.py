"""Fire N requests at genuinely the same moment.

A thread pool alone is not enough: without a barrier the first requests are already
answered before the last are sent, and a read-then-write race never opens. Every
worker blocks on the barrier and is released together.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar("T")


def burst(fn: Callable[[int], T], n: int, *, timeout: float = 60.0) -> list[T]:
    """Call `fn(i)` in batches of at most 50, each batch released together. Preserve order.

    An exception in a worker is returned in place of its result rather than raised,
    so a single transport error does not hide the other 49 outcomes.
    """
    if n < 1:
        raise ValueError("burst size must be positive")
    if n > 50:
        results = []
        for start in range(0, n, 50):
            results.extend(burst(lambda i, offset=start: fn(offset + i), min(50, n-start), timeout=timeout))
        return results
    barrier = threading.Barrier(n)

    def worker(index: int):
        try:
            barrier.wait(timeout=timeout)
        except threading.BrokenBarrierError:
            pass
        try:
            return fn(index)
        except Exception as exc:  # reported, not swallowed
            return exc

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(worker, range(n)))


def statuses(responses) -> list[int]:
    """HTTP status of each result; an exception counts as 0 so it shows up."""
    return [getattr(r, "status_code", 0) for r in responses]


def tally(responses) -> dict[int, int]:
    counts: dict[int, int] = {}
    for status in statuses(responses):
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def no_5xx(responses) -> None:
    bad = [r for r in responses if getattr(r, "status_code", 0) >= 500]
    errors = [r for r in responses if isinstance(r, Exception)]
    assert not bad and not errors, (
        f"5xx or transport errors under load: {tally(responses)}; "
        f"first error: {errors[0] if errors else bad[0].text[:200]}")
