"""Fixture builders for `pocketful`.

Every amount is an integer count of minor units. Nothing here ever produces a
float: a floating-point amount fails the first three-way split of an odd number.
"""
from __future__ import annotations

CURRENCIES = {"EUR": 2, "JPY": 0, "BHD": 3}

ADA = {"id": "u_ada", "email": "ada@example.com", "password": "correct horse",
       "display_name": "Ada", "handle": "ada", "balance": 10_000}
BOB = {"id": "u_bob", "email": "bob@example.com", "password": "correct horse",
       "display_name": "Bob", "handle": "bob", "balance": 2_500}
CY = {"id": "u_cy", "email": "cy@example.com", "password": "correct horse",
      "display_name": "Cy", "handle": "cy", "balance": 500}


def user(handle: str, balance: int, *, uid: str | None = None,
         email: str | None = None, display_name: str | None = None) -> dict:
    return {
        "id": uid or f"u_{handle}",
        "email": email or f"{handle}@example.com",
        "password": "correct horse",
        "display_name": display_name or handle.title(),
        "handle": handle,
        "balance": balance,
    }


def fixture(*, users: list[dict] | None = None, currency: str = "EUR",
            minor_units: int | None = None,
            payments: list[dict] | None = None,
            requests: list[dict] | None = None) -> dict:
    return {
        "currency": currency,
        "minor_units": CURRENCIES[currency] if minor_units is None else minor_units,
        "users": [ADA, BOB, CY] if users is None else users,
        "payments": payments or [],
        "requests": requests or [],
    }


def seeded_total(fx: dict) -> int:
    """The sum the harness compares every wallet against after a burst."""
    return sum(u["balance"] for u in fx["users"])


def equal_split(amount: int, n: int) -> list[int]:
    """The §9 rule: base toward zero, then one extra unit to the first `remainder`.

    The reference the tests assert against -- shares always sum to `amount`.
    """
    base = amount // n if amount >= 0 else -((-amount) // n)
    remainder = amount - base * n
    return [base + (1 if i < remainder else 0) for i in range(n)]
