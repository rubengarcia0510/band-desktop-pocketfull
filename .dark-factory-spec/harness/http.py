"""HTTP client and shared response assertions.

Every 4xx/5xx body in both tracks is ``{"error": {"code": ..., "message": ...}}``.
The suites assert on status and ``code`` and never on ``message``.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

REQUEST_TIMEOUT = 5.0   # spec: per-request timeout
RESET_TIMEOUT = 10.0    # spec: POST /_test/reset gets 10s


def new_key() -> str:
    """A fresh idempotency key. Valid range is 1..255 characters."""
    return uuid.uuid4().hex


class Api:
    """Thin wrapper over httpx carrying a bearer token and the spec's timeouts.

    Not reused across threads: stage 3 builds one Api per simulated client, which
    is also what the spec means by several clients signed in as the same user.
    """

    def __init__(self, base_url: str, token: str | None = None,
                 timeout: float = REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Api":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def request(self, method: str, path: str, *, json: Any = None,
                content: bytes | str | None = None,
                idempotency_key: str | None = None,
                token: str | None = ..., headers: dict | None = None,
                params: dict | None = None,
                timeout: float | None = None) -> httpx.Response:
        hdrs = dict(headers or {})
        # token=None explicitly means "send no Authorization header"; the
        # default sentinel means "use this client's token".
        effective = self.token if token is ... else token
        if effective is not None:
            hdrs.setdefault("Authorization", f"Bearer {effective}")
        if idempotency_key is not None:
            hdrs.setdefault("Idempotency-Key", idempotency_key)
        if json is not None or content is not None:
            hdrs.setdefault("Content-Type", "application/json")
        kwargs: dict = {"headers": hdrs}
        if json is not None:
            kwargs["json"] = json
        if content is not None:
            kwargs["content"] = content
        if params is not None:
            kwargs["params"] = params
        if timeout is not None:
            kwargs["timeout"] = timeout
        return self._client.request(method, path, **kwargs)

    def get(self, path: str, **kw) -> httpx.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> httpx.Response:
        return self.request("POST", path, **kw)

    def patch(self, path: str, **kw) -> httpx.Response:
        return self.request("PATCH", path, **kw)

    # ---- auth ------------------------------------------------------------
    def signup(self, email: str, password: str, display_name: str) -> httpx.Response:
        return self.post("/auth/signup", json={
            "email": email, "password": password, "display_name": display_name},
            token=None)

    def login(self, email: str, password: str) -> httpx.Response:
        return self.post("/auth/login", json={"email": email, "password": password},
                         token=None)

    def authenticate(self, email: str, password: str) -> "Api":
        """Log in and keep the token on this client. Raises if login fails."""
        resp = self.login(email, password)
        assert_status(resp, 200)
        self.token = resp.json()["token"]
        return self


# ---- assertions ----------------------------------------------------------

def _describe(resp: httpx.Response) -> str:
    body = resp.text
    if len(body) > 400:
        body = body[:400] + "..."
    return f"{resp.request.method} {resp.request.url.path} -> {resp.status_code} {body!r}"


def assert_status(resp: httpx.Response, expected: int) -> httpx.Response:
    assert resp.status_code == expected, \
        f"expected {expected}, got {resp.status_code}. {_describe(resp)}"
    return resp


def error_code(resp: httpx.Response) -> str:
    """The `error.code` of a failure response, asserting the envelope shape."""
    try:
        body = resp.json()
    except ValueError:
        raise AssertionError(f"error body is not JSON. {_describe(resp)}") from None
    assert isinstance(body, dict) and isinstance(body.get("error"), dict), \
        f"error body must be {{'error': {{'code': ...}}}}. {_describe(resp)}"
    code = body["error"].get("code")
    assert isinstance(code, str) and code, \
        f"error.code must be a non-empty string. {_describe(resp)}"
    return code


def assert_error(resp: httpx.Response, status: int, code: str) -> httpx.Response:
    """Assert an error response's status and `error.code` together.

    Both are asserted in one place so a failure reports the actual code rather
    than only the status, which is what makes a wrong-code failure debuggable.
    """
    actual = error_code(resp) if 400 <= resp.status_code < 600 else None
    assert resp.status_code == status and actual == code, (
        f"expected {status} {code}, got {resp.status_code} {actual}. {_describe(resp)}")
    return resp


def assert_no_5xx(resp: httpx.Response) -> httpx.Response:
    assert resp.status_code < 500, f"5xx is always a failure. {_describe(resp)}"
    return resp
