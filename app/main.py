from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="openrecon-api")

app.add_middleware(CORSMiddleware)


@app.get("/")
def root():
    return {"message": "OpenRecon API is running"}
