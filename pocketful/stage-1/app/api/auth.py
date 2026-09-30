"""POST /auth/signup, POST /auth/login (spec §6)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..services import auth_service

router = APIRouter()


@router.post("/auth/signup", status_code=201)
def signup(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    user, token = auth_service.signup(
        email=payload.get("email"),
        password=payload.get("password"),
        display_name=payload.get("display_name"),
    )
    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "token": token,
    }


@router.post("/auth/login")
def login(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    user, token = auth_service.login(
        email=payload.get("email"),
        password=payload.get("password"),
    )
    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "token": token,
    }


__all__ = ["router"]
