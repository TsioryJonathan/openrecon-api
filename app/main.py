from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine
from app.routers import sherlock

from app import models


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        print(Base.metadata.tables.keys())
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="OpenRecon API",
    description="API de reconnaissance OSINT pour retrouver les traces d'un utilisateur sur le web. "
    "Utilise sherlock-project pour scanner plus de 480 plateformes.",
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


@app.get("/", summary="Health check")
def root():
    return {"message": "OpenRecon API is running"}
