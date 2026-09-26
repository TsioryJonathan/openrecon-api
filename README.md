# OpenRecon API

OSINT reconnaissance API. Modular, correlated, evidence-backed recon engine.

- **Sherlock** : username presence on 480 platforms (rust `sherlock-rs`; live count on `GET /api/sherlock/sites`)
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
| `USER_SIGNING_SECRET` | yes (prod) | none    | Shared HMAC secret for identity assertions; 503 if unset |
| `AUTH_ALLOW_DEGRADED` | no       | false   | Local dev only: allow requests with **no** identity headers |
| `PORT`                | no       | 10000   | Server port |

`CORS_ORIGINS`, `API_KEY`, `USER_SIGNING_SECRET` and `AUTH_ALLOW_DEGRADED`
must be set in the Render dashboard for the public deployment.
`USER_SIGNING_SECRET` must match the UI's secret of the same name.

### Auth

Two layers protect `/api/investigations/*` (both required):

1. **API key** : the `X-API-Key` header must match `API_KEY`. If `API_KEY`
   is unset → `503 API_KEY not configured` (fail-closed, never "open").
2. **HMAC-signed user identity** : three headers, injected server-to-server
   by the OpenRecon UI proxy (never exposed to the browser) and verified
   before use:
   - `X-User-Id` : the authenticated user id;
   - `X-User-Exp` : unix expiry (issued now + 300s, 30s clock skew allowed);
   - `X-User-Sig` : hex `HMAC-SHA256("{user_id}:{exp}", USER_SIGNING_SECRET)`.

   The signature is compared in constant time. A bare `X-User-Id` (or a
   tampered/expired assertion) → `401 Unauthorized`; missing
   `USER_SIGNING_SECRET` → `503` (fail-closed). Holding only the API key is
   no longer enough to assert a user id.

   `AUTH_ALLOW_DEGRADED=true` (local development only) additionally allows
   requests where all three headers are **entirely absent** (`owner_id` is
   then `None`). Partial or invalid headers are still rejected.

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

## Tests

```bash
uv run pytest          # unit tests (hermetic, no database required)
uv run ruff check app/ tests/
```

CI runs both on every push/PR to `dev` and `main`.

## License

[MIT](LICENSE) © Tsiory Jonathan