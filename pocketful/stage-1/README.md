# Stage 1

Containerized HTTP service for the Stage 1 workspace.

## Implemented

- Health check
- Test reset endpoint
- User signup and login
- Authentication
- User balance inspection
- Payment creation
- Payment request creation and listing
- Integer minor-unit balance handling
- SQLite persistence with WAL
- Atomic SQLite write transactions
- Idempotency keys with canonical request-body hashing
- Idempotency replay and conflict handling
- Automated unit, API, idempotency, transaction, and verification tests

## Run with Docker

    docker build -t pocketful-stage-1 .
    docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage-1

The service listens on 0.0.0.0:8080.

Health check:

    curl http://localhost:8080/health

Expected response: {"status":"ok"}

## Local development

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8080

Run the tests:

    source .venv/bin/activate
    pytest
