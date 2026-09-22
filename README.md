# OpenRecon API

OSINT reconnaissance API. Modular, correlated, evidence-backed recon engine.

- **Sherlock** : username presence on 480+ platforms (rust `sherlock-rs`)
- **Dork** : Google dork query generation per category
- **EXIF** : metadata + GPS extraction from images
- **Recon** : IP/DNS enrichment
- **Investigations** : targets, per-target scans, adaptive scans, correlation across targets, markdown reports

Stack : FastAPI, SQLAlchemy (async), PostgreSQL (Neon), alembic, uv.

## Setup

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 10000
```

### Environment

| Variable        | Required | Default | Description |
|-----------------|----------|---------|-------------|
| `DATABASE_URL`  | yes      | -       | Async Postgres URL (`postgresql+asyncpg://...`) |
| `CORS_ORIGINS`  | no       | none    | Comma-separated allowed origins |
| `API_KEY`       | no       | none    | When set, all `/api/*` routes require the `X-API-Key` header |
| `PORT`          | no       | 10000   | Server port |

`CORS_ORIGINS` and `API_KEY` must be set in the Render dashboard for the public deployment.

### Auth

Set `API_KEY=secret-value` on the server. Every `/api/*` request must then send
`X-API-Key: secret-value`. Health check (`GET /`), `/openapi.yaml` and
`/docs` stay public. When `API_KEY` is unset the API is open.

## Deployment

The `Dockerfile` is a single-stage build that compiles `sherlock-rs`
(from Rust) into the image. Expected to move to multi-stage later.

## API docs

Interactive docs at `/docs`. Live spec at `openapi.yaml` (auto-regenerated).