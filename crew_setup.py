"""
Base de la banda de agentes para el hackathon Dark Factory.

Los mandatos de los agentes son genéricos a propósito (regla del hackathon):
no mencionan pocketful, wallets, transfers, ni ningún detalle del track.
El detalle específico del track va en la TAREA que le pasás al Planner
al ejecutar el script (ver ROOM_BRIEF más abajo), nunca en el mandato.
"""

import os
from typing import Mapping

from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM

REQUIRED_ENV_VARS = (
    "FEATHERLESS_API_KEY",
    "FEATHERLESS_BASE_URL",
    "FEATHERLESS_MODEL",
)


def require_env_vars(env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    missing = [key for key in REQUIRED_ENV_VARS if not str(source.get(key, "")).strip()]

    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(
            "Faltan variables de entorno requeridas para Featherless: "
            f"{missing_list}. Creá un archivo .env a partir de .env.example y "
            "completá tu API key real antes de correr el script."
        )

    return {key: str(source[key]).strip() for key in REQUIRED_ENV_VARS}


def build_llm(env: Mapping[str, str] | None = None) -> LLM:
    values = require_env_vars(env)
    try:
        return LLM(
            model=values["FEATHERLESS_MODEL"],
            base_url=values["FEATHERLESS_BASE_URL"],
            api_key=values["FEATHERLESS_API_KEY"],
        )
    except Exception as exc:
        raise RuntimeError(
            "No se pudo inicializar el LLM de Featherless. Revisá "
            "FEATHERLESS_API_KEY, FEATHERLESS_BASE_URL y FEATHERLESS_MODEL. "
            "Asegurate de que la API key sea válida y de que el modelo elegido "
            "exista en el catálogo de Featherless."
        ) from exc


def build_agents(llm: LLM):
    planner = Agent(
        role="Planner",
        goal=(
            "Recibir una tarea y una especificación, y descomponerlas en "
            "subtareas chicas y ordenadas por dependencia, cada una lo bastante "
            "acotada para que un solo agente la resuelva sin ambigüedad."
        ),
        backstory=(
            "Sos meticuloso: nunca asumís lo que la especificación no dice "
            "explícitamente. Para cada subtarea indicás qué evidencia concreta "
            "debe entregar quien la ejecute para considerarla terminada. Si algo "
            "es ambiguo, lo señalás en vez de decidir por tu cuenta."
        ),
        llm=llm,
        verbose=True,
    )

    implementer = Agent(
        role="Implementer",
        goal=(
            "Implementar el cambio mínimo necesario para cumplir una subtarea "
            "concreta, dentro del alcance exacto que se le indicó."
        ),
        backstory=(
            "No tocás nada fuera del alcance de tu subtarea. Al terminar, "
            "entregás evidencia concreta de que funciona (salida de comandos, "
            "tests corridos, logs) — nunca una afirmación sin respaldo. Si la "
            "subtarea depende de algo no resuelto todavía, lo reportás en vez "
            "de improvisar."
        ),
        llm=llm,
        verbose=True,
    )

    verifier = Agent(
        role="Verifier",
        goal=(
            "Verificar de forma independiente si un entregable cumple su "
            "criterio de aceptación, sin confiar en el reporte de quien "
            "implementó."
        ),
        backstory=(
            "Ejecutás vos mismo las pruebas que correspondan. Devolvés un "
            "veredicto (aprobado/rechazado) con la evidencia que lo sustenta. "
            "Si rechazás, especificás exactamente qué falló, sin proponer vos "
            "la corrección."
        ),
        llm=llm,
        verbose=True,
    )

    return planner, implementer, verifier


def build_crew(task_description: str) -> Crew:
    """
    Arma la crew con una tarea concreta. `task_description` es donde va
    TODO el detalle específico del track (endpoints, spec, criterios de
    aceptación) — nunca en los mandatos de arriba.
    """
    llm = build_llm()
    planner, implementer, verifier = build_agents(llm)

    plan_task = Task(
        description=task_description,
        expected_output="Una lista de subtareas ordenadas, cada una con su criterio de evidencia.",
        agent=planner,
    )

    implement_task = Task(
        description="Implementá cada subtarea del plan, en orden.",
        expected_output="El código correspondiente + evidencia de que funciona.",
        agent=implementer,
        context=[plan_task],
    )

    verify_task = Task(
        description="Verificá de forma independiente cada entregable del Implementer.",
        expected_output="Veredicto aprobado/rechazado por subtarea, con evidencia.",
        agent=verifier,
        context=[implement_task],
    )

    return Crew(
        agents=[planner, implementer, verifier],
        tasks=[plan_task, implement_task, verify_task],
        process=Process.sequential,
        verbose=True,
    )


if __name__ == "__main__":
    load_dotenv()

    # Ejemplo de prueba local (reemplazá por la spec real de la etapa 1
    # de pocketful cuando salga el 26/9).
    ROOM_BRIEF = """
    [PEGÁ ACÁ la tarea concreta: spec de la etapa, endpoints, criterios
    de aceptación. Esto es solo para probar el flujo localmente antes
    de conectar la banda a BAND Desktop.]
    """

    try:
        crew = build_crew(ROOM_BRIEF)
        result = crew.kickoff()
        print(result)
    except ValueError as exc:
        print(f"Error de configuración: {exc}")
        raise SystemExit(1)
    except Exception as exc:
        print(f"No se pudo iniciar la banda: {exc}")
        raise SystemExit(1)
