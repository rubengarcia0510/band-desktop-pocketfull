"""Runner for the three Band seats used by the dark factory.

Planner uses CrewAI for planning.
Implementer and Verifier use OpenCode so they can inspect and modify/verify
the repository through the filesystem and shell.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

from band import Agent
from band.adapters import CrewAIAdapter, OpencodeAdapter, OpencodeAdapterConfig

from crew_setup import ensure_agents, require_env_vars


SEAT_ROLE_BY_NAME = {
    "planner": "Planner",
    "implementer": "Implementer",
    "verifier": "Verifier",
}


def _seat_config(seat_name: str) -> dict[str, str | None]:
    load_dotenv()

    seat = seat_name.lower()

    if seat not in SEAT_ROLE_BY_NAME:
        raise ValueError(f"Seat desconocido: {seat_name}")

    return {
        "agent_id": os.getenv(f"{seat.upper()}_AGENT_ID"),
        "api_key": os.getenv(f"{seat.upper()}_API_KEY"),
        "role": SEAT_ROLE_BY_NAME[seat],
    }


def _require_seat_env(seat_name: str) -> dict[str, str]:
    config = _seat_config(seat_name)

    missing = [
        key
        for key in ("agent_id", "api_key")
        if not str(config.get(key, "") or "").strip()
    ]

    if missing:
        raise ValueError(
            f"Faltan variables de entorno para {seat_name}: {', '.join(missing)}"
        )

    return {
        "agent_id": str(config["agent_id"]).strip(),
        "api_key": str(config["api_key"]).strip(),
    }


def _build_planner_adapter(
    selected_role: str,
    model_name: str,
) -> OpencodeAdapter:
    return _build_coding_adapter()


def _build_coding_adapter() -> OpencodeAdapter:
    repository_directory = os.path.dirname(os.path.abspath(__file__))

    config = OpencodeAdapterConfig(
        base_url=os.getenv(
            "OPENCODE_BASE_URL",
            "http://127.0.0.1:4096",
        ),
        directory=repository_directory,
        provider_id="featherless",
        model_id=os.getenv(
            "OPENCODE_MODEL",
            "MiniMaxAI/MiniMax-M2.5",
        ),
        approval_mode="auto_accept",
        turn_timeout_s=float(
            os.getenv(
                "OPENCODE_TURN_TIMEOUT_S",
                "900",
            )
        ),
    )

    return OpencodeAdapter(config=config)


def build_band_agent(
    seat_name: str,
    *,
    event_role: str | None = None,
) -> Agent:
    """Create a Band seat using the appropriate agent adapter."""

    seat_name = seat_name.lower()

    credentials = _require_seat_env(seat_name)

    llm_config = require_env_vars()

    os.environ["OPENAI_API_KEY"] = llm_config["FEATHERLESS_API_KEY"]
    os.environ["OPENAI_API_BASE"] = llm_config["FEATHERLESS_BASE_URL"]

    selected_role = event_role or SEAT_ROLE_BY_NAME[seat_name]

    if seat_name in {"implementer", "verifier"}:
        adapter = _build_coding_adapter()
    else:
        adapter = _build_planner_adapter(
            selected_role,
            llm_config["FEATHERLESS_MODEL"],
        )

    return Agent.create(
        adapter=adapter,
        agent_id=credentials["agent_id"],
        api_key=credentials["api_key"],
    )


async def _run_seat(seat_name: str) -> None:
    agent = build_band_agent(seat_name)

    await agent.run()


if __name__ == "__main__":
    seat = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "planner"
    ).lower()

    try:
        asyncio.run(_run_seat(seat))
    except KeyboardInterrupt:
        print(f"Seat {seat} detenida por el usuario.")
    except Exception as exc:  # pragma: no cover - CLI entrypoint
        print(f"Error al arrancar {seat}: {exc}")
        raise SystemExit(1)
