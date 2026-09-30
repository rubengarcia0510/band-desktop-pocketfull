# stage-1 — Pocketful Stage 1 slice

Containerized HTTP service implementing the wallet/payments domain from
`band-ai/dark-factory-wearedevs` → `pocketful/spec/stage-1.md`.

## Status

| Subtask | Scope | Status |
|---|---|---|
| ST-1.1 | Recon + scaffolding (`/health`, `POST /_test/reset`, container, run/test) | scaffolded |
| ST-1.2 | Users + balances in integer minor units + invariants | pending |
| ST-1.3 | Atomic transfers + idempotency + auth (TBD per Planner rule "spec manda") | pending |
| ST-1.4 | Activity feed with visibility rules | pending |
| ST-1.5 | Concurrency safety + idempotent retries under load | pending |

## Container

```bash
docker build -t pocketful-stage-1 .
docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage-1
```

See `RUN.md` for the single-line build + start.

## Local dev

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Tests:

```bash
source .venv/bin/activate
pytest
```
