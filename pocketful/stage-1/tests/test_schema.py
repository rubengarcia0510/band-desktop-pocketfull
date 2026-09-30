"""ST-1 schema smoke tests (Subtask 2).

These tests are deliberately synchronous — they only inspect the on-disk
SQLite schema after the app boots and after a reset.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Tables required by spec §1 for Stage 1 persistence.
REQUIRED_TABLES = frozenset(
    {"payments", "payment_requests", "splits", "settlements", "idempotency_keys"}
)


def test_required_tables_present_after_init():
    from app.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    missing = REQUIRED_TABLES - names
    assert not missing, f"missing tables after init: {missing}"


def test_idempotency_keys_preserve_original_key_and_body_hash():
    """Spec §7: store the original key (not the hash) plus a body-hash column."""
    from app.db import get_connection

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users(id, email, password_hash, display_name, handle, balance, currency, minor_units, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                "u_idem",
                "idem@example.com",
                "x" * 60,
                "Idem",
                "idem",
                0,
                "EUR",
                2,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO idempotency_keys(user_id, endpoint, key, request_body_hash, response_status, response_body, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                "u_idem",
                "POST /payments",
                "client-chosen-key-abc",
                "h1",
                201,
                "{}",
                now,
            ),
        )
    finally:
        conn.execute("COMMIT")

    row = conn.execute(
        "SELECT key, request_body_hash FROM idempotency_keys "
        "WHERE user_id=? AND endpoint=?",
        ("u_idem", "POST /payments"),
    ).fetchone()
    assert row is not None
    assert row["key"] == "client-chosen-key-abc", "original key must be preserved verbatim"
    assert row["request_body_hash"] == "h1"


def test_payments_amount_column_is_integer_minor_units():
    """Spec §4: amounts are integer minor units, no FLOAT."""
    from app.db import get_connection

    conn = get_connection()
    cols = {
        r["name"]: r["type"].upper()
        for r in conn.execute("PRAGMA table_info(payments)").fetchall()
    }
    assert cols["amount"] == "INTEGER", f"payments.amount is {cols['amount']}, expected INTEGER"


def test_idempotency_keys_pk_is_user_endpoint_key():
    """Spec §7: idempotency scoped by (user, method, path, key)."""
    from app.db import get_connection

    conn = get_connection()
    pk = conn.execute("PRAGMA table_info(idempotency_keys)").fetchall()
    cols = [r["name"] for r in pk]
    pk_cols = [r["name"] for r in pk if r["pk"] > 0]
    assert set(pk_cols) == {"user_id", "endpoint", "key"}, f"PK cols: {pk_cols}"
    assert "request_body_hash" in cols
