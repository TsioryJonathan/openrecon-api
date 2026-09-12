from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.sherlock import run_sherlock

router = APIRouter()


class SearchRequest(BaseModel):
    username: str


@router.post("/search")
async def search_username(body: SearchRequest, db: AsyncSession = Depends(get_db)):
    results = await run_sherlock(body.username, db)
    return {"username": body.username, "results": results}
