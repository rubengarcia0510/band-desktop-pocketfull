"""POST /payments (spec §8)."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Body, Depends, Header, Response
from fastapi.responses import JSONResponse

from ..auth import current_user_id
from ..errors import raise_error
from ..models.balance import AmountError
from ..services import payment_service

router = APIRouter()


@router.post("/payments")
def create_payment(
    user_id: Annotated[str, Depends(current_user_id)],
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    payload: dict[str, Any] = Body(default_factory=dict),
) -> JSONResponse:
    if not idempotency_key:
        raise_error(400, "missing_idempotency_key", "Idempotency-Key header is required")
    if not isinstance(idempotency_key, str) or len(idempotency_key) > 255:
        raise_error(422, "validation_failed", "Idempotency-Key must be 1-255 characters")

    try:
        response, status = payment_service.create_payment(
            user_id=user_id,
            idempotency_key=idempotency_key,
            to_handle=payload.get("to_handle"),
            amount=payload.get("amount"),
            note=payload.get("note", ""),
            visibility=payload.get("visibility", "public"),
        )
    except AmountError as e:
        raise_error(422, "validation_failed", str(e))
    return JSONResponse(content=response, status_code=status)


__all__ = ["router"]
