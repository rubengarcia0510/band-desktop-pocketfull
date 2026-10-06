"""Stage-1 scaffold. The same floor for every track: `toy`, `tablekeeper`,
`pocketful`.

A starting point, not an implementation. It does the three things the harness needs
in order to talk to you at all -- bind `PORT`, answer `/health`, accept a fixture on
`/_test/reset` -- plus signup and login, so the suite can get far enough to tell you
something useful. Every other endpoint answers 501 `not_implemented`.

Run the harness against it and you get a legible list of what is missing. That list
is your backlog. Replace this file, or grow it; nothing here is precious, and no part
of it is the answer.
"""
from __future__ import annotations

try:
    from .passwords import hash_password, verify_password
except ImportError:
    from passwords import hash_password, verify_password

import json
import os
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

STATE: dict = {"fixture": {}, "users": {}, "by_email": {}, "tokens": {}}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # ---- plumbing you can keep ----
    def send_json(self, status: int, payload) -> None:
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def fail(self, status: int, code: str) -> None:
        """Every 4xx and 5xx carries this shape. See the spec, §5."""
        self.send_json(status, {"error": {"code": code, "message": code}})

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except ValueError:
            return None          # caller turns this into 400 malformed_request

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PATCH(self):
        self.route("PATCH")

    def route(self, method: str) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"

        # --- the three the harness needs before anything else works ---
        if method == "GET" and path == "/health":
            return self.send_json(200, {"status": "ok"})

        if method == "POST" and path == "/_test/reset":
            fixture = self.body()
            if fixture is None:
                return self.fail(400, "malformed_request")
            # Delete all state and load the fixture. Synchronous: when you return
            # 204 the next request must see this fixture and nothing else.
            STATE["fixture"] = {k: v for k, v in fixture.items() if k != "users"}
            STATE["users"] = {}
            STATE["by_email"] = {}
            STATE["tokens"] = {}
            for user in fixture.get("users", []):
                user = {**user, "password": hash_password(user["password"])}
                STATE["users"][user["id"]] = user
                STATE["by_email"][user["email"].lower()] = user
            return self.send_json(204, None)

        # --- auth, so the suite can reach your endpoints at all ---
        if method == "POST" and path == "/auth/signup":
            return self.signup()
        if method == "POST" and path == "/auth/login":
            return self.login()

        # --- everything else is yours to write ---
        return self.fail(501, "not_implemented")

    def signup(self):
        data = self.body()
        if data is None:
            return self.fail(400, "malformed_request")
        email, password = data.get("email"), data.get("password")
        if not isinstance(email, str) or not isinstance(password, str):
            return self.fail(400, "malformed_request")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+", email) or len(password) < 8:
            return self.fail(422, "validation_failed")
        if email.lower() in STATE["by_email"]:
            return self.fail(409, "email_taken")
        user = {"id": f"u_{uuid.uuid4().hex[:8]}", "email": email,
                "password": hash_password(password), "display_name": data.get("display_name")}
        STATE["users"][user["id"]] = user
        STATE["by_email"][email.lower()] = user
        token = uuid.uuid4().hex
        STATE["tokens"][token] = user["id"]
        return self.send_json(201, {"user_id": user["id"],
                                    "display_name": user["display_name"],
                                    "token": token})

    def login(self):
        data = self.body()
        if data is None:
            return self.fail(400, "malformed_request")
        user = STATE["by_email"].get(str(data.get("email", "")).lower())
        if user is None or not verify_password(data.get("password"), user["password"]):
            return self.fail(401, "unauthenticated")
        token = uuid.uuid4().hex
        STATE["tokens"][token] = user["id"]
        return self.send_json(200, {"user_id": user["id"],
                                    "display_name": user["display_name"],
                                    "token": token})


class Server(ThreadingHTTPServer):
    # The harness may have 50 requests in flight. The stdlib default of 5 drops
    # connections well below that -- a real source of phantom stage-3 failures.
    request_queue_size = 256
    daemon_threads = True


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))     # the harness sets PORT
    print(f"scaffold listening on 0.0.0.0:{port}", flush=True)
    Server(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
