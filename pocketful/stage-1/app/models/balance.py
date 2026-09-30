"""Amount invariants (spec §4 arithmetic range)."""

from __future__ import annotations

from typing import Final

MAX_AMOUNT: Final[int] = 1_000_000_000
MIN_AMOUNT: Final[int] = 1
ALLOWED_MINOR_UNITS: Final[frozenset[int]] = frozenset({0, 2, 3})


class AmountError(ValueError):
    """Raised when an amount fails spec validation (422 validation_failed)."""


def validate_amount(value: object) -> int:
    """Coerce + validate an amount.

    Spec §4: ``1000``, ``1000.0`` and ``1e3`` are all valid and represent the
    same minor-unit count. Booleans and strings are invalid.
    """
    if isinstance(value, bool):
        raise AmountError("amount must be a number, got bool")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise AmountError("amount must be an integer")
        amount = int(value)
    else:
        raise AmountError("amount must be a number")
    if amount < MIN_AMOUNT:
        raise AmountError("amount must be at least 1")
    if amount > MAX_AMOUNT:
        raise AmountError(f"amount must be at most {MAX_AMOUNT}")
    return amount


def validate_minor_units(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AmountError("minor_units must be an integer in {0, 2, 3}")
    if value not in ALLOWED_MINOR_UNITS:
        raise AmountError(f"minor_units must be one of {sorted(ALLOWED_MINOR_UNITS)}")
    return value


__all__ = [
    "AmountError",
    "MAX_AMOUNT",
    "MIN_AMOUNT",
    "ALLOWED_MINOR_UNITS",
    "validate_amount",
    "validate_minor_units",
]
