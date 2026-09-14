from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html

from app.db.database import Base, engine
from app.routers import sherlock
from app.schemas import MessageResponse

from app import models

OPENAPI_PATH = Path(__file__).parent.parent / "openapi.json"


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
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sherlock.router, prefix="/api/sherlock", tags=["Sherlock"])


@app.get("/", response_model=MessageResponse, summary="Health check")
def root():
    return {"message": "OpenRecon API is running"}


@app.get("/openapi.json", include_in_schema=False)
def get_openapi_spec():
    import json
    return json.loads(OPENAPI_PATH.read_text())
