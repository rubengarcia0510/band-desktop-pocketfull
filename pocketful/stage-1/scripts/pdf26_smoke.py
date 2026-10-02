"""PDF-26 single entrypoint smoke.

Stage 1 acceptance evidence: after running this script
  - the SQLite database file exists at the requested path;
  - the spec-mandated tables are present and the schema has been
    applied idempotently (a second run is a no-op).

Run from anywhere:
    python3 pocketful/stage-1/scripts/pdf26_smoke.py

Exits 0 on success, non-zero on failure.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import db as db_mod  # noqa: E402


REQUIRED_TABLES = frozenset(
    {"payments", "payment_requests", "splits", "settlements", "idempotency_keys"}
)


def main() -> int:
    fd, path = tempfile.mkstemp(prefix="pdf26-", suffix=".db")
    os.close(fd)
    os.remove(path)
    wal = path + "-wal"
    shm = path + "-shm"
    for p in (wal, shm):
        if os.path.exists(p):
            os.remove(p)

    print(f"db_path = {path}")

    conn = db_mod.connect(path)
    assert isinstance(conn, sqlite3.Connection), "connect() must return sqlite3.Connection"

    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal.lower() == "wal", f"expected WAL journal mode, got {journal!r}"
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert int(fk) == 1, f"expected foreign_keys=ON, got {fk!r}"

    db_mod.init_schema(conn)
    conn.close()

    assert os.path.exists(path), f"SQLite file was not created at {path}"
    size = os.path.getsize(path)
    assert size > 0, f"SQLite file is empty: {path}"
    print(f"file created, size = {size} bytes")

    verify = sqlite3.connect(path)
    verify.row_factory = sqlite3.Row
    names = {
        r["name"]
        for r in verify.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    verify.close()
    missing = REQUIRED_TABLES - names
    assert not missing, f"missing required tables: {sorted(missing)}"
    print(f"tables present ({len(REQUIRED_TABLES)} required): {sorted(REQUIRED_TABLES)}")

    again = db_mod.connect(path)
    db_mod.init_schema(again)
    again.close()
    print("schema bootstrap is idempotent on a second run")

    for p in (path, wal, shm):
        if os.path.exists(p):
            os.remove(p)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
