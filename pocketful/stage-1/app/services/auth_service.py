"""Signup, login and handle derivation (spec §4, §6)."""

from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timezone

import bcrypt

from .. import auth as auth_mod
from .. import db as db_mod
from ..errors import raise_error
from ..models.balance import AmountError, validate_amount, validate_minor_units
from ..models.user import UserRecord

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+$")
HANDLE_REGEX = re.compile(r"^[a-z0-9_]{1,20}$")
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 200
MAX_DISPLAY_NAME_LEN = 64


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_handle(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    sanitized = re.sub(r"[^a-z0-9_]", "_", local)
    if not sanitized:
        raise_error(422, "validation_failed", "email local part cannot be empty")
    return sanitized[:20]


def _new_user_id(prefix: str = "u") -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _validate_email(email: object) -> str:
    if not isinstance(email, str) or not EMAIL_REGEX.match(email):
        raise_error(422, "validation_failed", "email must be of the form local@domain")
    return email


def _validate_password(password: object) -> str:
    if not isinstance(password, str):
        raise_error(422, "validation_failed", "password must be a string")
    if len(password) < MIN_PASSWORD_LEN:
        raise_error(422, "validation_failed", "password must be at least 8 characters")
    if len(password) > MAX_PASSWORD_LEN:
        raise_error(422, "validation_failed", "password must be at most 200 characters")
    return password


def _validate_display_name(name: object) -> str:
    if not isinstance(name, str):
        raise_error(422, "validation_failed", "display_name must be a string")
    if not name:
        raise_error(422, "validation_failed", "display_name is required")
    if len(name) > MAX_DISPLAY_NAME_LEN:
        raise_error(422, "validation_failed", f"display_name must be at most {MAX_DISPLAY_NAME_LEN} characters")
    return name


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def _user_from_row(row: sqlite3.Row | None) -> UserRecord | None:
    if row is None:
        return None
    return UserRecord(**dict(row))


def signup(
    email: object,
    password: object,
    display_name: object,
    currency: object = "EUR",
    minor_units: object = 2,
    balance: object = 0,
) -> tuple[UserRecord, str]:
    email_s = _validate_email(email)
    password_s = _validate_password(password)
    display_name_s = _validate_display_name(display_name)
    try:
        balance_i = validate_amount(balance) if balance else 0
    except AmountError as exc:
        raise_error(422, "validation_failed", str(exc))
    try:
        minor_units_i = validate_minor_units(minor_units)
    except AmountError as exc:
        raise_error(422, "validation_failed", str(exc))

    handle = derive_handle(email_s)
    conn = db_mod.get_connection()
    existing_email = conn.execute("SELECT id FROM users WHERE email = ?", (email_s,)).fetchone()
    if existing_email is not None:
        raise_error(409, "email_taken", "email already registered")

    user_id = _new_user_id()
    created_at = _utc_now_iso()
    password_hash = _hash_password(password_s)

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO users(id, email, password_hash, display_name, handle, balance, currency, minor_units, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                email_s,
                password_hash,
                display_name_s,
                handle,
                balance_i,
                str(currency),
                minor_units_i,
                created_at,
            ),
        )
        token = auth_mod.issue_token(conn, user_id, created_at)
        conn.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        conn.execute("ROLLBACK")
        msg = str(exc).lower()
        if "users.email" in msg:
            raise_error(409, "email_taken", "email already registered")
        if "users.handle" in msg:
            raise_error(409, "handle_taken", "handle derived from email is already taken")
        raise_error(422, "validation_failed", "invalid signup payload")

    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    user = _user_from_row(row)
    assert user is not None
    return user, token


def login(email: object, password: object) -> tuple[UserRecord, str]:
    if not isinstance(email, str):
        raise_error(401, "unauthenticated", "wrong email or password")
    if not isinstance(password, str):
        raise_error(401, "unauthenticated", "wrong email or password")
    conn = db_mod.get_connection()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
        raise_error(401, "unauthenticated", "wrong email or password")
    user = _user_from_row(row)
    assert user is not None
    created_at = _utc_now_iso()
    token = auth_mod.issue_token(conn, user.id, created_at)
    return user, token


__all__ = [
    "signup",
    "login",
    "derive_handle",
    "HANDLE_REGEX",
    "EMAIL_REGEX",
    "MIN_PASSWORD_LEN",
]
