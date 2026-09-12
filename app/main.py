from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.sherlock import router as sherlock_router

app = FastAPI(title="openrecon-api")

app.add_middleware(CORSMiddleware)

app.include_router(sherlock_router, prefix="/api/sherlock")


@app.get("/")
def root():
    return {"message": "OpenRecon API is running"}
