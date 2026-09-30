"""Bearer-token authentication dependency (spec §6).

Tokens are opaque strings issued at signup/login. They do not expire; an
account may have multiple valid tokens. Look-up is by exact match in the
``tokens`` table.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db as db_mod
from .errors import raise_error
from .models.user import UserRecord

_bearer = HTTPBearer(auto_error=False)


def issue_token(conn, user_id: str, created_at: str) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO tokens(token, user_id, created_at) VALUES(?, ?, ?)",
        (token, user_id, created_at),
    )
    return token


def _extract_bearer(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    return credentials.credentials


def current_user_id(
    token: Annotated[str | None, Depends(_extract_bearer)],
) -> str:
    if not token:
        raise_error(401, "unauthenticated", "missing or malformed bearer token")
    conn = db_mod.get_connection()
    row = conn.execute(
        "SELECT user_id FROM tokens WHERE token = ?", (token,)
    ).fetchone()
    if row is None:
        raise_error(401, "unauthenticated", "unknown bearer token")
    return row["user_id"]


def current_user(
    user_id: Annotated[str, Depends(current_user_id)],
) -> UserRecord:
    conn = db_mod.get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise_error(401, "unauthenticated", "token references a missing user")
    return UserRecord(**dict(row))


__all__ = ["issue_token", "current_user_id", "current_user"]
