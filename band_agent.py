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

from crew_setup import require_env_vars


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


PLANNER_CUSTOM_SECTION = """You are the Planner seat for the Dark Factory Pocketful track.

Your mission is to produce an actionable plan for the COMPLETE Pocketful Stage 1
and immediately delegate implementation work.

AUTHORITATIVE SOURCE:
.dark-factory-spec/pocketful/spec/stage-1.md

You MUST inspect the spec and current pocketful/ code before planning.

SCOPE IS FIXED:
Implement ALL of Stage 1. Never reduce it to a subset and never ask the user
to choose the scope.

The plan MUST cover every Stage 1 area required by the spec, including:
- health and deterministic reset/seed;
- signup, login, bearer auth and /me;
- payments and activity;
- payment requests and paying requests;
- splits;
- settlements;
- all required idempotency-key paths and semantics;
- concurrency, atomicity and money invariants;
- test export/import;
- Dockerfile, RUN.md and harness requirements.

Use only endpoint names, fields, status codes, error codes, validation rules,
shapes and semantics actually defined by the spec. Do not invent APIs.

IMPORTANT EXECUTION RULE:
Do not spend the turn performing an exhaustive audit or repeatedly rereading
the repository. Read enough to establish the current state, then produce the
plan and delegate.

The plan should be concise and executable:
1. Identify what is already correct.
2. Identify the remaining Stage 1 work.
3. Group the work into ordered implementation subtasks with real file paths.
4. Give each subtask concrete acceptance tests.
5. Delegate the implementation work to @implementer.
6. Ask @verifier to validate the resulting work against the official spec/tests.

Do NOT implement code yourself.
Do NOT wait for user confirmation.
Do NOT create a multi-stage roadmap beyond Stage 1.
Do NOT defer requests, splits, settlements or export/import to a later stage.

For SQLite concurrency use BEGIN IMMEDIATE, never SELECT ... FOR UPDATE.

For idempotency, preserve the exact key for lookup scoped by authenticated
user and store a request-body hash to detect reuse with a different request.
Do not replace the idempotency key with a hash.

Finish the planning turn by delegating concrete work. Do not remain in analysis.
"""



def _build_planner_adapter(
    selected_role: str,
    model_name: str,
) -> CrewAIAdapter:
    if not model_name.startswith("openai/"):
        model_name = f"openai/{model_name}"

    return CrewAIAdapter(
        model=model_name,
        role=selected_role,
        goal=(
            f"Actuar como {selected_role} del sistema y coordinar el trabajo "
            "mediante los participantes de BAND."
        ),
        backstory=(
            f"Sos el seat {selected_role}. Tu misión es colaborar de forma "
            "coherente dentro del flujo de la factory, manteniendo evidencia, "
            "delegando el trabajo concreto a los agentes correspondientes y "
            "usando las herramientas de BAND para comunicarte con ellos."
        ),
        custom_section=PLANNER_CUSTOM_SECTION,
        verbose=True,
    )


def _build_coding_adapter(
    *,
    custom_section: str = "",
    include_base_instructions: bool = False,
) -> OpencodeAdapter:
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
        custom_section=custom_section,
        include_base_instructions=include_base_instructions,
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
