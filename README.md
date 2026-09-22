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

| Variable              | Required | Default | Description |
|-----------------------|----------|---------|-------------|
| `DATABASE_URL`        | yes      | -       | Async Postgres URL (`postgresql+asyncpg://...`) |
| `CORS_ORIGINS`        | no       | none    | Comma-separated allowed origins |
| `API_KEY`             | yes (prod) | none    | Required by `/api/investigations/*`; 503 if unset |
| `AUTH_ALLOW_DEGRADED` | no       | false   | When `true`, skips the `X-User-Id` check (local dev only) |
| `PORT`                | no       | 10000   | Server port |

`CORS_ORIGINS`, `API_KEY` and `AUTH_ALLOW_DEGRADED` must be set in the Render dashboard for the public deployment.

### Auth

Two layers protect `/api/investigations/*` (both required):

1. **API key** : the `X-API-Key` header must match `API_KEY`. If `API_KEY`
   is unset → `503 API_KEY not configured` (fail-closed, never "open").
2. **User isolation** : the `X-User-Id` header must carry the authenticated
   user id (injected server-to-server by the OpenRecon UI proxy, never
   exposed to the browser). When absent → `401 Unauthorized`, unless
   `AUTH_ALLOW_DEGRADED=true` (local development only).

All `/api/investigations/*` routes scope every query by `X-User-Id` :
an investigation owned by another user is treated as non-existent (`404`),
so existence cannot be probed. Legacy rows with `owner_id = NULL` are
invisible to authenticated requests.

The standalone modules (`/api/sherlock`, `/api/dork`, `/api/exif`,
`/api/recon`, `/api/scan`) are **public** (no auth).

The health check (`GET /`), `/openapi.yaml` and `/docs` stay public.

## Deployment

The `Dockerfile` is a single-stage build that compiles `sherlock-rs`
(from Rust) into the image. Expected to move to multi-stage later.

## API docs

Interactive docs at `/docs`. Live spec at `openapi.yaml` (auto-regenerated).