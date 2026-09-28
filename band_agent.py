"""Runner for the three Band seats used by the dark factory.

This module keeps the CrewAI integration generic and exposes the same three
seats as module-level symbols so callers can do:

    python band_agent.py planner
    python band_agent.py implementer
    python band_agent.py verifier
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

from band import Agent
from band.adapters import CrewAIAdapter

from crew_setup import ensure_agents, require_env_vars


SEAT_ROLE_BY_NAME = {
    "planner": "Planner",
    "implementer": "Implementer",
    "verifier": "Verifier",
}


def _seat_config(seat_name: str) -> dict[str, str | None]:
    load_dotenv()
    seat = seat_name.lower()
    return {
        "agent_id": os.getenv(f"{seat.upper()}_AGENT_ID"),
        "api_key": os.getenv(f"{seat.upper()}_API_KEY"),
        "role": SEAT_ROLE_BY_NAME[seat],
    }


def _require_seat_env(seat_name: str) -> dict[str, str]:
    config = _seat_config(seat_name)
    if config is None:
        raise ValueError(f"Seat desconocido: {seat_name}")

    missing = [
        key
        for key in ("agent_id", "api_key")
        if not str(config.get(key, "") or "").strip()
    ]
    if missing:
        raise ValueError(
            f"Faltan variables de entorno para {seat_name}: {', '.join(missing)}"
        )
    return {"agent_id": str(config["agent_id"]).strip(), "api_key": str(config["api_key"]).strip()}


def build_band_agent(seat_name: str, *, event_role: str | None = None) -> Agent:
    """Create a Band seat backed by the matching CrewAI agent.

    The real Band SDK factory is `Agent.create(adapter=..., agent_id=..., api_key=...)`.
    The `agent` keyword is not a valid parameter.
    """
    seat_name = seat_name.lower()
    credentials = _require_seat_env(seat_name)
    llm_config = require_env_vars()
    os.environ["OPENAI_API_KEY"] = llm_config["FEATHERLESS_API_KEY"]
    os.environ["OPENAI_API_BASE"] = llm_config["FEATHERLESS_BASE_URL"]

    model_name = llm_config["FEATHERLESS_MODEL"]
    if not model_name.startswith("openai/"):
        model_name = f"openai/{model_name}"

    planner, implementer, verifier = ensure_agents()

    agent_lookup = {
        "planner": planner,
        "implementer": implementer,
        "verifier": verifier,
    }
    agent_lookup[seat_name]
    selected_role = event_role or _seat_config(seat_name)["role"]

    adapter = CrewAIAdapter(
        model=model_name,
        role=selected_role,
        goal=f"Actuar como {selected_role} del sistema." ,
        backstory=(
            f"Sos el seat {selected_role}. Tu misión es colaborar de forma "
            "coherente dentro del flujo de la factory, manteniendo evidencia y "
            "verificación independiente."
        ),
        verbose=True,
    )

    return Agent.create(
        adapter=adapter,
        agent_id=credentials["agent_id"],
        api_key=credentials["api_key"],
    )


async def _run_seat(seat_name: str) -> None:
    agent = build_band_agent(seat_name)
    await agent.start()
    try:
        await agent.run_forever()
    finally:
        await agent.stop()


if __name__ == "__main__":
    seat = (sys.argv[1] if len(sys.argv) > 1 else "planner").lower()
    try:
        asyncio.run(_run_seat(seat))
    except KeyboardInterrupt:
        print(f"Seat {seat} detenida por el usuario.")
    except Exception as exc:  # pragma: no cover - CLI entrypoint
        print(f"Error al arrancar {seat}: {exc}")
        raise SystemExit(1)
