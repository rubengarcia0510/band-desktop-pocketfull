# pocketful-band — base de agentes (Dark Factory)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate         # en Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Completá `.env` con tu API key real de Featherless (la que te llega por mail
al registrarte en el hackathon) y elegí un modelo del catálogo de Featherless
en `FEATHERLESS_MODEL`.

## Probar localmente

Antes de conectar esto a BAND Desktop, probalo suelto para validar que los
3 agentes (Planner → Implementer → Verifier) se pasan bien la posta:

```bash
python crew_setup.py
```

Editá la variable `ROOM_BRIEF` dentro de `crew_setup.py` con una tarea de
prueba chica (no hace falta que sea de pocketful todavía).

## Conectar a Band (band-sdk + CrewAIAdapter)

1. Instalá el extra de CrewAI del SDK (en su propio venv, choca con parlant/pydantic-ai):
   ```bash
   pip install "band-sdk[crewai]"
   ```
2. Andá a `app.band.ai`, creá un "remote agent" por cada seat (Planner,
   Implementer, Verifier) y copiá el UUID + API key de cada uno a tu `.env`.
3. Revisá `band_agent.py` — tiene un TODO marcado donde no tengo 100%
   confirmado el nombre exacto del parámetro que `CrewAIAdapter` espera.
   Antes de correrlo en serio, fijate el ejemplo real que instala el
   paquete (carpeta `examples/crewai/` del repo `band-sdk-python`) y
   ajustá si difiere.
4. Corré cada seat en su propia terminal:
   ```bash
   python band_agent.py planner
   python band_agent.py implementer
   python band_agent.py verifier
   ```
5. Abrí Band, creá una room, agregá los 3 agentes como participantes, y
   ahí es donde se van a coordinar.

No tengo confirmado si esto reemplaza del todo a Band Desktop o convive
con él (Band Desktop parece más orientado al plugin de Claude Code) —
puede que igual necesites tener Band Desktop abierto para ver el board,
aunque los seats corran vía SDK. Confirmalo mirando la app una vez que
tengas la room armada.

## Reglas del hackathon a no olvidar

- Los **mandatos** (`role`, `goal`, `backstory` de cada Agent) deben ser
  genéricos — nada de "pocketful", "wallet", "endpoint", data-testid, etc.
  Todo el detalle específico del track va en `task_description` al llamar
  a `build_crew(...)`.
- Mínimo 3 seats distintos (ya están: Planner, Implementer, Verifier).
- Guardá el export de la room (`harness export-room`) y el video con la
  grabación de BAND Desktop — sin eso, descalifica.
