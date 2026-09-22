import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.auth import get_current_user_id, require_api_key
from app.routers import dork, exif, investigation, recon, scan, sherlock
from app.schemas import MessageResponse

INVESTIGATION_DEPS = [Depends(require_api_key), Depends(get_current_user_id)]

OPENAPI_PATH = Path(__file__).parent.parent / "openapi.yaml"

import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
    force=True,
)
for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
    lg = logging.getLogger(logger_name)
    lg.setLevel(logging.INFO)
    lg.propagate = True

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started (migrations disabled)")
    yield


app = FastAPI(
    title="OpenRecon API",
    description=("OSINT reconnaissance API. Modular, correlated, evidence-backed recon engine."),
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = (time.perf_counter() - start) * 1000
        logger.exception(
            "%s %s FAILED %.1fms",
            request.method,
            request.url.path,
            duration,
        )
        raise
    duration = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


app.include_router(sherlock.router, prefix="/api/sherlock", tags=["Sherlock"])
app.include_router(dork.router, prefix="/api/dork", tags=["Dork"])
app.include_router(exif.router, prefix="/api/exif", tags=["EXIF"])
app.include_router(recon.router, prefix="/api/recon", tags=["Recon"])
app.include_router(scan.router, prefix="/api/scan", tags=["Scan"])
app.include_router(
    investigation.router,
    prefix="/api/investigations",
    tags=["Investigations"],
    dependencies=INVESTIGATION_DEPS,
)


@app.get("/", response_model=MessageResponse, summary="Health check")
def root():
    return {"message": "OpenRecon API is running"}


@app.get("/openapi.yaml", include_in_schema=False)
def get_openapi_spec():
    return PlainTextResponse(OPENAPI_PATH.read_text(), media_type="text/yaml")


@app.get("/docs", include_in_schema=False)
def swagger_ui():
    return get_swagger_ui_html(openapi_url="/openapi.yaml", title="OpenRecon API")


@app.get("/redoc", include_in_schema=False)
def redoc_ui():
    return get_redoc_html(openapi_url="/openapi.yaml", title="OpenRecon API")
