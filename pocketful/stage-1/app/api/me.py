"""GET /me — returns the authenticated user's public profile and balance."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..auth import current_user
from ..models.user import UserRecord, UserPublic

router = APIRouter()


@router.get("/me")
def me(user: Annotated[UserRecord, Depends(current_user)]) -> dict:
    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "handle": user.handle,
        "balance": user.balance,
        "currency": user.currency,
        "minor_units": user.minor_units,
    }


__all__ = ["router"]
