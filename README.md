# pocketful-band — base de agentes (Dark Factory)

## Setup

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Windows (PowerShell)

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Completá `.env` con tu API key real de Featherless (la que te llega por mail
al registrarte en el hackathon) y elegí un modelo del catálogo de Featherless
en `FEATHERLESS_MODEL`.

Las variables esperadas por el proyecto son:

```env
FEATHERLESS_API_KEY=tu_api_key
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_MODEL=featherless-ai/Qwen/Qwen2.5-72B-Instruct
```

La biblioteca `litellm` es necesaria para que CrewAI acepte modelos OpenAI-compatible custom como los de Featherless.

## Probar localmente

Antes de conectar esto a BAND Desktop, probalo suelto para validar que los
3 agentes (Planner → Implementer → Verifier) se pasan bien la posta:

```bash
python crew_setup.py
```

Editá la variable `ROOM_BRIEF` dentro de `crew_setup.py` con una tarea de
prueba chica (no hace falta que sea de pocketful todavía).

## ⚠️ Pendiente: conectar a BAND Desktop

Este script corre standalone. Para que cuente como submission válida del
hackathon, la banda tiene que vivir en BAND Desktop (registrada como
"seats" reales, con su room, su export, etc.) — no alcanza con correrlo
suelto en tu terminal.

Falta confirmar cómo se conecta un agente CrewAI al **BAND SDK** (adaptador
mencionado en la info del hackathon, pero sin documentación confirmada acá).
Preguntá en el Discord de BAND por el adaptador de CrewAI antes de dar esto
por terminado.

## Reglas del hackathon a no olvidar

- Los **mandatos** (`role`, `goal`, `backstory` de cada Agent) deben ser
  genéricos — nada de "pocketful", "wallet", "endpoint", data-testid, etc.
  Todo el detalle específico del track va en `task_description` al llamar
  a `build_crew(...)`.
- Mínimo 3 seats distintos (ya están: Planner, Implementer, Verifier).
- Guardá el export de la room (`harness export-room`) y el video con la
  grabación de BAND Desktop — sin eso, descalifica.
