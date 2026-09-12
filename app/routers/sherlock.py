from fastapi import APIRouter
from pydantic import BaseModel

from app.services.sherlock import run_sherlock

router = APIRouter()


class SearchRequest(BaseModel):
    username: str


@router.post("/search")
async def search_username(body: SearchRequest):
    results = await run_sherlock(body.username)
    return {"username": body.username, "results": results}
