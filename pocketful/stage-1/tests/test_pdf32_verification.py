"""Independent verification tests for PDF-32 idempotency decision.

Verifier-authored, not implementer-authored. Each acceptance criterion is
checked explicitly.
"""
import json
import sqlite3
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.idempotency.decision import decide, claim, update_response, Decision, ClaimResult
from app.idempotency.repository import Outcome, store as repo_store
from app.idempotency.canonical_hash import canonical_body_hash
from app.sqlite_utils.transaction import write_transaction, run_in_write_transaction


@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / "verify.db")
    c = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA busy_timeout = 5000")
    c.execute(
        "CREATE TABLE users ("
        "id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,"
        "display_name TEXT NOT NULL, handle TEXT NOT NULL UNIQUE, balance INTEGER NOT NULL DEFAULT 0,"
        "currency TEXT NOT NULL, minor_units INTEGER NOT NULL, created_at TEXT NOT NULL)"
    )
    with write_transaction(c) as cur:
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)",
            ("u_a", "a@x", "x", "A", "a", 0, "EUR", 2, "2026-01-01T00:00:00+00:00"),
        )
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)",
            ("u_b", "b@x", "x", "B", "b", 0, "EUR", 2, "2026-01-01T00:00:00+00:00"),
        )
    from app.idempotency.schema import apply_schema
    apply_schema(c)
    yield c
    c.close()


def _body(amount=100):
    return {"to": "x", "amount": amount}


# AC1: key preserved verbatim (never replaced by hash)
def test_ac1_key_preserved_verbatim_with_special_chars(conn):
    raw_key = "client:abc/def?ghi=!#$%&*+="  # unusual characters
    repo_store(conn, user_id="u_a", endpoint="POST /payments",
               key=raw_key, body=_body(), response_status=201,
               response_body='{"ok":1}', created_at="2026-01-01T00:00:00+00:00")
    # Inspect actual row in DB
    row = conn.execute(
        "SELECT key, request_body_hash FROM idempotency_keys WHERE user_id = ?",
        ("u_a",),
    ).fetchone()
    assert row["key"] == raw_key, "key must be stored byte-for-byte"
    assert row["key"] != row["request_body_hash"], "key must NOT be conflated with hash"
    # Length of hash is 64; raw_key length is much less
    assert len(row["request_body_hash"]) == 64


# AC2: scoping by user_id AND endpoint
def test_ac2_user_scoping(conn):
    body = _body()
    repo_store(conn, user_id="u_a", endpoint="POST /payments",
               key="k1", body=body, response_status=201,
               response_body='{"x":1}', created_at="2026-01-01T00:00:00+00:00")
    # Same key, same body, different user -> MISSING
    d = decide(conn, user_id="u_b", endpoint="POST /payments", key="k1", body=body)
    assert d.is_missing, f"different user must MISSING, got {d.outcome}"


def test_ac2_endpoint_scoping(conn):
    body = _body()
    repo_store(conn, user_id="u_a", endpoint="POST /payments",
               key="k2", body=body, response_status=201,
               response_body='{"x":1}', created_at="2026-01-01T00:00:00+00:00")
    # Same key, same user, different endpoint -> MISSING
    d = decide(conn, user_id="u_a", endpoint="POST /requests", key="k2", body=body)
    assert d.is_missing, f"different endpoint must MISSING, got {d.outcome}"


# AC3: canonical body hash stored
def test_ac3_canonical_body_hash_stored(conn):
    body = _body()
    repo_store(conn, user_id="u_a", endpoint="POST /payments",
               key="k3", body=body, response_status=201,
               response_body='{"ok":1}', created_at="2026-01-01T00:00:00+00:00")
    row = conn.execute(
        "SELECT request_body_hash FROM idempotency_keys WHERE user_id='u_a' AND key='k3'"
    ).fetchone()
    expected = canonical_body_hash(body)
    assert row["request_body_hash"] == expected


# AC4: same key + same canonical body -> REPLAY (returns stored response)
def test_ac4_same_body_replay_returns_stored_response(conn):
    body = _body(42)
    stored = json.dumps({"payment_id": "p_777", "amount": 42})
    repo_store(conn, user_id="u_a", endpoint="POST /payments",
               key="k4", body=body, response_status=201,
               response_body=stored, created_at="2026-01-01T00:00:00+00:00")
    d = decide(conn, user_id="u_a", endpoint="POST /payments", key="k4", body=body)
    assert d.is_replay
    assert d.response_status == 201
    assert d.response_body == stored
    assert d.response_payload == {"payment_id": "p_777", "amount": 42}


# AC5: same key + different canonical body -> CONFLICT
def test_ac5_different_body_conflict(conn):
    repo_store(conn, user_id="u_a", endpoint="POST /payments",
               key="k5", body=_body(100), response_status=201,
               response_body='{"ok":1}', created_at="2026-01-01T00:00:00+00:00")
    d = decide(conn, user_id="u_a", endpoint="POST /payments", key="k5", body=_body(200))
    assert d.is_conflict, f"different body must CONFLICT, got {d.outcome}"


# AC6: all writes use run_in_write_transaction (BEGIN IMMEDIATE)
def test_ac6_writes_use_begin_immediate(conn):
    """Verify by monkey-patching run_in_write_transaction to record calls."""
    calls = {"n": 0, "wraps": []}
    real = run_in_write_transaction

    def spy(c, func):
        calls["n"] += 1
        calls["wraps"].append(func)
        return real(c, func)

    import app.idempotency.repository as repo_mod
    orig_store = repo_mod.run_in_write_transaction
    orig_update = repo_mod.run_in_write_transaction
    # The repository module imports the symbol directly:
    repo_mod.run_in_write_transaction = spy
    try:
        # Trigger store and update_response through the decision module
        claim(conn, user_id="u_a", endpoint="POST /payments",
              key="k6", body=_body(), response_status=201,
              response_body="", created_at="2026-01-01T00:00:00+00:00")
        update_response(conn, user_id="u_a", endpoint="POST /payments",
                        key="k6", response_status=201,
                        response_body='{"final":true}')
    finally:
        repo_mod.run_in_write_transaction = orig_store
    # claim uses run_in_write_transaction for the store insert (1 call),
    # update_response uses it too (1 call) -> total 2
    assert calls["n"] == 2, f"expected 2 write-transaction calls (store + update), got {calls['n']}"

    # Confirm transaction.py actually issues BEGIN IMMEDIATE
    src = open(os.path.join(os.path.dirname(__file__), "..", "app",
                            "sqlite_utils", "transaction.py")).read()
    assert "BEGIN IMMEDIATE" in src


# AC7: No SELECT ... FOR UPDATE
def test_ac7_no_select_for_update_anywhere():
    base = os.path.join(os.path.dirname(__file__), "..", "app")
    pattern = re.compile(r"\bSELECT\b[^\n]*\bFOR\s+UPDATE\b", re.IGNORECASE)
    for root, _dirs, files in os.walk(base):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                src = open(p, encoding="utf-8").read()
                # Strip docstrings first
                src_no_doc = re.sub(r'"""[\s\S]*?"""', "", src)
                src_no_doc = re.sub(r"'''[\s\S]*?'''", "", src_no_doc)
                # Strip line comments
                for line in src_no_doc.splitlines():
                    stripped = line.split("#", 1)[0]
                    if pattern.search(stripped):
                        pytest.fail(f"FOR UPDATE in executable code: {p}: {line!r}")


# AC8: Standard library only
def test_ac8_stdlib_only():
    base = os.path.join(os.path.dirname(__file__), "..", "app")
    allowed = {"__future__", "json", "sqlite3", "dataclasses", "typing",
               "contextlib", "hashlib", "re", "collections", "functools",
               "itertools", "pathlib", "os", "sys"}
    suspicious = []
    for root, _dirs, files in os.walk(base):
        if "__pycache__" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            if "idempotency" not in root and "sqlite_utils" not in root:
                continue
            src = open(os.path.join(root, f), encoding="utf-8").read()
            # Strip docstrings
            src_no_doc = re.sub(r'"""[\s\S]*?"""', "", src)
            src_no_doc = re.sub(r"'''[\s\S]*?'''", "", src_no_doc)
            for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", src_no_doc, re.M):
                top = m.group(1)
                if top in allowed or top in {"app"}:
                    continue
                suspicious.append(f"{os.path.join(root, f)}: {top}")
    assert not suspicious, f"non-stdlib imports in idempotency/sqlite_utils: {suspicious}"


# Bonus: verify update_response round-trips correctly
def test_update_response_roundtrip(conn):
    body = _body()
    cr = claim(conn, user_id="u_a", endpoint="POST /payments",
               key="kup", body=body, response_status=201,
               response_body="", created_at="2026-01-01T00:00:00+00:00")
    assert cr.is_winner
    update_response(conn, user_id="u_a", endpoint="POST /payments",
                    key="kup", response_status=201,
                    response_body='{"final":42}')
    d = decide(conn, user_id="u_a", endpoint="POST /payments", key="kup", body=body)
    assert d.is_replay
    assert d.response_payload == {"final": 42}
