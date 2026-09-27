"""
Conecta cada seat de tu crew (Planner, Implementer, Verifier) a Band como
un agente independiente, usando el CrewAIAdapter del band-sdk.

Corré este script UNA VEZ POR SEAT, en 3 terminales/procesos separados,
pasando el nombre del seat como argumento:

    python band_agent.py planner
    python band_agent.py implementer
    python band_agent.py verifier

Cada seat necesita su propio agent_id + api_key, creados antes en
app.band.ai (un "remote agent" por seat). Ver .env.example.

⚠️ Nota de honestidad: no tengo confirmado el nombre exacto de todos los
parámetros que acepta CrewAIAdapter (la doc pública que encontré muestra
el patrón general, pero no el detalle completo del constructor). Antes
de correr esto en serio, revisá el ejemplo real que se instala junto con
el paquete:

    pip install "band-sdk[crewai]"
    # el ejemplo queda en algo como:
    # <tu-venv>/lib/.../site-packages o el repo band-sdk-python, carpeta examples/crewai/

y ajustá la construcción de `CrewAIAdapter(...)` de abajo a lo que ese
ejemplo muestre si difiere.
"""

import os
import sys
import asyncio

from dotenv import load_dotenv
from band import Agent
from band.adapters import CrewAIAdapter

# Reusa los 3 agentes genéricos que ya definiste en crew_setup.py
from crew_setup import planner, implementer, verifier

load_dotenv()

SEATS = {
    "planner": {
        "crewai_agent": planner,
        "agent_id_env": "PLANNER_AGENT_ID",
        "api_key_env": "PLANNER_API_KEY",
    },
    "implementer": {
        "crewai_agent": implementer,
        "agent_id_env": "IMPLEMENTER_AGENT_ID",
        "api_key_env": "IMPLEMENTER_API_KEY",
    },
    "verifier": {
        "crewai_agent": verifier,
        "agent_id_env": "VERIFIER_AGENT_ID",
        "api_key_env": "VERIFIER_API_KEY",
    },
}


async def main(seat_name: str) -> None:
    if seat_name not in SEATS:
        raise SystemExit(f"Seat desconocido: {seat_name}. Usá uno de: {list(SEATS)}")

    seat = SEATS[seat_name]

    # TODO: confirmar contra el ejemplo real de examples/crewai/ si el
    # parámetro se llama `agent`, `crew_agent`, o distinto.
    adapter = CrewAIAdapter(agent=seat["crewai_agent"])

    agent = Agent.create(
        adapter=adapter,
        agent_id=os.environ[seat["agent_id_env"]],
        api_key=os.environ[seat["api_key_env"]],
    )

    print(f"[{seat_name}] conectando a Band...")
    await agent.run()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python band_agent.py <planner|implementer|verifier>")
    asyncio.run(main(sys.argv[1]))
