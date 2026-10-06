"""User data shapes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserRecord:
    """Internal storage shape — includes the password hash."""

    id: str
    email: str
    password_hash: str
    display_name: str
    handle: str
    balance: int
    currency: str
    minor_units: int
    created_at: str


@dataclass(frozen=True)
class UserPublic:
    """Public-facing shape — never includes the password hash."""

    id: str
    display_name: str
    handle: str
    balance: int
    currency: str
    minor_units: int


__all__ = ["UserRecord", "UserPublic"]
