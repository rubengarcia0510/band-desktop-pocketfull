"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os


def get_port() -> int:
    raw = os.environ.get("PORT", "8080").strip()
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"PORT must be an integer, got {raw!r}") from exc
    if not (1 <= port <= 65535):
        raise RuntimeError(f"PORT must be in 1..65535, got {port}")
    return port
