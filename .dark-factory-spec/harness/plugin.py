"""Pytest plugin shared by both tracks.

A track's `test/conftest.py` enables it with:

    pytest_plugins = ["harness.plugin"]

It supplies the base URL, a client factory, and `reset` -- the fixture loader that
every test calls before it asserts anything.
"""
from __future__ import annotations

import json
import pathlib
from urllib.parse import urlsplit

import httpx
import pytest

from harness.http import Api, RESET_TIMEOUT, assert_status


def pytest_addoption(parser):
    group = parser.getgroup("dark factory harness")
    group.addoption("--base-url", action="store", default=None,
                    help="Base URL of the service under test, e.g. http://127.0.0.1:8080")
    group.addoption("--previous-base-url", default=None,
                    help="preceding stage's service, used to produce upgrade snapshots")


    group.addoption("--harness-summary", default=None, help="write check counts as JSON")


_COUNTS = {}
_PASSED = {}   # node id -> whether that check passed; filtered-out checks did not


def pytest_configure(config):
    _COUNTS.clear()
    _PASSED.clear()
    _COUNTS.update(collected=0, passed=0, failed=0, errors=0, skipped=0, deselected=0, xfailed=0)
    config.addinivalue_line("markers", "stage(n): the stage this test belongs to")


def pytest_deselected(items):
    _COUNTS["deselected"] += len(items)
    _PASSED.update((item.nodeid, False) for item in items)


def pytest_collection_finish(session):
    _COUNTS["collected"] = len(session.items) + _COUNTS["deselected"]
    for item in session.items:
        _PASSED.setdefault(item.nodeid, False)


def pytest_collectreport(report):
    if report.failed:
        _COUNTS["errors"] += 1
    elif report.skipped:
        _COUNTS["skipped"] += 1


def pytest_runtest_logreport(report):
    if getattr(report, "wasxfail", None):
        _COUNTS["xfailed"] += 1
    elif report.skipped:
        _COUNTS["skipped"] += 1
    elif report.failed:
        _COUNTS["failed" if report.when == "call" else "errors"] += 1
    elif report.when == "call" and report.passed:
        _COUNTS["passed"] += 1
    if report.failed or getattr(report, "wasxfail", None):
        _PASSED[report.nodeid] = False
    elif report.when == "call" and report.passed:
        _PASSED[report.nodeid] = True


def pytest_sessionfinish(session, exitstatus):
    path = session.config.getoption("--harness-summary")
    if path:
        files = {}
        for nodeid, passed in _PASSED.items():
            result = files.setdefault(nodeid.split("::", 1)[0], {"passed": 0, "total": 0})
            result["total"] += 1
            result["passed"] += passed
        pathlib.Path(path).write_text(json.dumps({**_COUNTS, "files": files}) + "\n")


@pytest.fixture(scope="session")
def base_url(request) -> str:
    url = request.config.getoption("--base-url")
    if not url:
        pytest.fail("--base-url is required (or run through `python -m harness run`)")
    return url.rstrip("/")


@pytest.fixture
def reset(base_url):
    """POST /_test/reset with a fixture body. Returns the response.

    The spec requires this to be synchronous: when it returns 204 the next request
    must see the fixture and nothing else. Tests rely on that, so a non-204 here
    fails the test rather than being silently tolerated -- except when a test is
    deliberately checking a rejected fixture, which uses `raw=True`.
    """
    def _reset(fixture: dict, *, raw: bool = False) -> httpx.Response:
        resp = httpx.post(f"{base_url}/_test/reset", json=fixture, timeout=RESET_TIMEOUT)
        if not raw:
            assert_status(resp, 204)
        return resp
    return _reset


@pytest.fixture
def api(base_url):
    """Factory for API clients. Every client made here is closed at teardown."""
    made: list[Api] = []

    def _api(token: str | None = None) -> Api:
        client = Api(base_url, token=token)
        made.append(client)
        return client

    yield _api
    for client in made:
        client.close()


@pytest.fixture
def anon(api):
    """An unauthenticated client."""
    return api()


@pytest.fixture
def previous_api(request):
    url = request.config.getoption('--previous-base-url')
    if not url:
        pytest.fail('upgrade checks require the preceding stage: use harness run --repo '
                    '--stage N, or supply --previous-base-url for development')
    with Api(url, timeout=RESET_TIMEOUT) as client:
        yield client


# ---- stage 2: the browser ------------------------------------------------

def browser_args(base_url: str) -> list[str]:
    """Chromium flags that make the service's origin a secure context.

    Loopback is always one, so a host-mode run gets secure-only APIs such as
    crypto.randomUUID; graders reach the service by container name over plain HTTP.
    Treating that origin as secure too makes both runs see the same browser.
    """
    parts = urlsplit(base_url)
    return [f"--unsafely-treat-insecure-origin-as-secure={parts.scheme}://{parts.netloc}"]


@pytest.fixture(scope="session")
def browser(base_url):
    """One headless Chromium for the whole stage-2 run.

    Full Chromium, not the default headless shell, which ignores `browser_args`.
    """
    from playwright import sync_api as playwright
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch(channel="chromium", args=browser_args(base_url))
        yield instance
        instance.close()


@pytest.fixture
def page(browser, base_url):
    """A fresh browser context per test, so no session leaks between them."""
    context = browser.new_context(base_url=base_url)
    context.set_default_timeout(10_000)
    tab = context.new_page()
    yield tab
    context.close()


@pytest.fixture
def tid():
    """`data-testid` selector. The suites find elements by these and nothing else."""
    return lambda name: f"[data-testid='{name}']"
