# Pocketful — Stage 1 slice

Build and start without manual setup:

```bash
docker build -t pocketful-stage-1 stage-1/ && \
docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage-1
```

The service listens on `0.0.0.0:${PORT}` (default `8080`). `GET /health`
returns `200 {"status":"ok"}` once the service is ready.
