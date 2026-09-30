"""SQLite database bootstrap with WAL mode for concurrent reads.

Storage is ephemeral (per spec §2: "Disk: ephemeral; state need not survive
a container restart"). On every boot we start from a clean file inside the
container's writable layer, so reset semantics are honored automatically.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Iterator

from .config import get_port


_DB_PATH_ENV = "POCKETFUL_DB_PATH"

_SCHEMA_VERSION = 2


def _default_db_path() -> str:
    env = os.environ.get(_DB_PATH_ENV)
    if env:
        return env
    return "/tmp/pocketful.db"


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path if db_path is not None else _default_db_path()
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA user_version")
    current = cur.fetchone()[0]
    if current >= _SCHEMA_VERSION:
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        if current < 1:
            _apply_v1(conn)
        if current < 2:
            _apply_v2(conn)
        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    finally:
        conn.execute("COMMIT")


def _apply_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "  id TEXT PRIMARY KEY,"
        "  email TEXT NOT NULL UNIQUE,"
        "  password_hash TEXT NOT NULL,"
        "  display_name TEXT NOT NULL,"
        "  handle TEXT NOT NULL UNIQUE,"
        "  balance INTEGER NOT NULL DEFAULT 0,"
        "  currency TEXT NOT NULL,"
        "  minor_units INTEGER NOT NULL,"
        "  created_at TEXT NOT NULL,"
        "  CHECK (balance >= 0),"
        "  CHECK (minor_units IN (0, 2, 3))"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_handle ON users(handle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tokens ("
        "  token TEXT PRIMARY KEY,"
        "  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "  created_at TEXT NOT NULL"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON tokens(user_id)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS service_meta ("
        "  key TEXT PRIMARY KEY,"
        "  value TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS payments ("
        "  id TEXT PRIMARY KEY,"
        "  from_user_id TEXT NOT NULL REFERENCES users(id),"
        "  to_user_id TEXT NOT NULL REFERENCES users(id),"
        "  amount INTEGER NOT NULL,"
        "  note TEXT NOT NULL DEFAULT '',"
        "  visibility TEXT NOT NULL DEFAULT 'public',"
        "  request_id TEXT,"
        "  settlement_id TEXT,"
        "  created_at TEXT NOT NULL"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_from ON payments(from_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_to ON payments(to_user_id)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS payment_requests ("
        "  id TEXT PRIMARY KEY,"
        "  requester_id TEXT NOT NULL REFERENCES users(id),"
        "  payer_id TEXT NOT NULL REFERENCES users(id),"
        "  amount INTEGER NOT NULL,"
        "  note TEXT NOT NULL DEFAULT '',"
        "  status TEXT NOT NULL DEFAULT 'pending',"
        "  payment_id TEXT REFERENCES payments(id),"
        "  created_at TEXT NOT NULL"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_requester ON payment_requests(requester_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_payer ON payment_requests(payer_id)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS splits ("
        "  id TEXT PRIMARY KEY,"
        "  user_id TEXT NOT NULL REFERENCES users(id),"
        "  amount INTEGER NOT NULL,"
        "  note TEXT NOT NULL DEFAULT '',"
        "  created_at TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settlements ("
        "  id TEXT PRIMARY KEY,"
        "  operator_id TEXT NOT NULL REFERENCES users(id),"
        "  committed_at TEXT NOT NULL,"
        "  created_at TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settlement_operators ("
        "  user_id TEXT PRIMARY KEY REFERENCES users(id)"
        ")"
    )


def _apply_v2(conn: sqlite3.Connection) -> None:
    # spec §7: idempotency keys are scoped to (user, endpoint, key).
    # The v1 schema keyed by (user, key) only — drop and recreate with the
    # correct PK so the same key on a different endpoint is a distinct record.
    conn.execute("DROP TABLE IF EXISTS idempotency_keys")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS idempotency_keys ("
        "  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "  endpoint TEXT NOT NULL,"
        "  key TEXT NOT NULL,"
        "  request_body_hash TEXT NOT NULL,"
        "  response_status INTEGER NOT NULL,"
        "  response_body TEXT NOT NULL,"
        "  created_at TEXT NOT NULL,"
        "  PRIMARY KEY (user_id, endpoint, key)"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_idem_user ON idempotency_keys(user_id)"
    )
    # split_participants records one row per participant of a split so we can
    # reconstruct shares + the resulting requests at read time.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS split_participants ("
        "  split_id TEXT NOT NULL REFERENCES splits(id) ON DELETE CASCADE,"
        "  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "  handle TEXT NOT NULL,"
        "  share_amount INTEGER NOT NULL,"
        "  request_id TEXT REFERENCES payment_requests(id) ON DELETE SET NULL,"
        "  PRIMARY KEY (split_id, user_id)"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_split_parts_split ON split_participants(split_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_split_parts_user ON split_participants(user_id)"
    )


def get_connection() -> sqlite3.Connection:
    """Module-level singleton used by the FastAPI app."""
    global _CONNECTION
    try:
        return _CONNECTION
    except NameError:
        pass
    _CONNECTION = connect()
    init_schema(_CONNECTION)
    return _CONNECTION


def reset_connection_for_tests(db_path: str) -> sqlite3.Connection:
    """Replace the module singleton; used by the test fixture."""
    global _CONNECTION
    if os.path.exists(db_path):
        os.remove(db_path)
    wal = db_path + "-wal"
    shm = db_path + "-shm"
    for p in (wal, shm):
        if os.path.exists(p):
            os.remove(p)
    _CONNECTION = connect(db_path)
    init_schema(_CONNECTION)
    return _CONNECTION


def iter_connection() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency that yields the singleton connection."""
    yield get_connection()
