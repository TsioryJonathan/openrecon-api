import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import PlainTextResponse

from app.db.database import Base, engine
from app.routers import sherlock
from app.schemas import MessageResponse

from app import models

OPENAPI_PATH = Path(__file__).parent.parent / "openapi.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        print(Base.metadata.tables.keys())
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="OpenRecon API",
    description="OSINT reconnaissance API to find a user's presence across the web. "
    "Uses sherlock-project to scan 480+ platforms.",
    version="0.1.0",
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

app.include_router(sherlock.router, prefix="/api/sherlock", tags=["Sherlock"])


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
