"""Payment creation with idempotency (spec §7, §8)."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from .. import db as db_mod
from ..errors import raise_error
from ..models.balance import validate_amount

ENDPOINT = "POST /payments"
MAX_NOTE_LEN = 200
ALLOWED_VISIBILITY = frozenset({"public", "private"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_body(body: dict) -> str:
    normalized = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _build_response(payment_row: dict, user_from: dict, user_to: dict) -> dict:
    return {
        "payment_id": payment_row["id"],
        "from_user_id": payment_row["from_user_id"],
        "from_handle": user_from["handle"],
        "to_user_id": payment_row["to_user_id"],
        "to_handle": user_to["handle"],
        "amount": payment_row["amount"],
        "currency": user_from["currency"],
        "note": payment_row["note"],
        "visibility": payment_row["visibility"],
        "request_id": payment_row["request_id"],
        "created_at": payment_row["created_at"],
    }


def create_payment(
    user_id: str,
    idempotency_key: str,
    to_handle: str,
    amount: object,
    note: object = "",
    visibility: object = "public",
) -> tuple[dict, int]:
    conn = db_mod.get_connection()
    body = {
        "to_handle": to_handle,
        "amount": amount,
        "note": note,
        "visibility": visibility,
    }
    body_hash = _hash_body(body)

    existing = conn.execute(
        "SELECT response_status, response_body FROM idempotency_keys "
        "WHERE user_id = ? AND endpoint = ? AND key = ?",
        (user_id, ENDPOINT, idempotency_key),
    ).fetchone()

    if existing is not None:
        stored_hash = conn.execute(
            "SELECT request_body_hash FROM idempotency_keys "
            "WHERE user_id = ? AND endpoint = ? AND key = ?",
            (user_id, ENDPOINT, idempotency_key),
        ).fetchone()["request_body_hash"]
        if stored_hash != body_hash:
            raise_error(409, "idempotency_key_reuse", "same key, different request body")
        return json.loads(existing["response_body"]), 200

    amount_i = validate_amount(amount)
    if not isinstance(note, str):
        raise_error(422, "validation_failed", "note must be a string")
    note_str = note
    if len(note_str) > MAX_NOTE_LEN:
        raise_error(422, "validation_failed", "note must be at most 200 characters")
    if not isinstance(visibility, str) or visibility not in ALLOWED_VISIBILITY:
        raise_error(422, "validation_failed", "visibility must be 'public' or 'private'")

    if to_handle == conn.execute(
        "SELECT handle FROM users WHERE id = ?", (user_id,)
    ).fetchone()["handle"]:
        raise_error(422, "self_payment", "cannot pay yourself")

    to_user = conn.execute(
        "SELECT id, handle, currency FROM users WHERE handle = ?", (to_handle,)
    ).fetchone()
    if to_user is None:
        raise_error(404, "not_found", "recipient user not found")

    from_user = conn.execute(
        "SELECT id, handle, balance, currency FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if from_user is None:
        raise_error(401, "unauthenticated", "sender user not found")

    if from_user["balance"] < amount_i:
        raise_error(409, "insufficient_funds", "not enough balance")

    payment_id = f"p_{secrets.token_hex(8)}"
    created_at = _utc_now_iso()

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?",
            (amount_i, user_id),
        )
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (amount_i, to_user["id"]),
        )
        conn.execute(
            "INSERT INTO payments(id, from_user_id, to_user_id, amount, note, visibility, request_id, settlement_id, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (payment_id, user_id, to_user["id"], amount_i, note_str, visibility, None, None, created_at),
        )
        conn.execute(
            "INSERT INTO idempotency_keys(user_id, endpoint, key, request_body_hash, response_status, response_body, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (user_id, ENDPOINT, idempotency_key, body_hash, 201, "", created_at),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    payment_row = conn.execute(
        "SELECT * FROM payments WHERE id = ?", (payment_id,)
    ).fetchone()
    response = _build_response(payment_row, from_user, to_user)
    response_json = json.dumps(response)

    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "UPDATE idempotency_keys SET response_body = ?, response_status = ? "
        "WHERE user_id = ? AND endpoint = ? AND key = ?",
        (response_json, 201, user_id, ENDPOINT, idempotency_key),
    )
    conn.execute("COMMIT")

    return response, 201


__all__ = ["create_payment"]
