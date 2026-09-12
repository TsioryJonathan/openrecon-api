from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.sherlock import get_results_by_username, run_sherlock

router = APIRouter()


class SearchRequest(BaseModel):
    username: str


@router.post("/search")
async def search_username(body: SearchRequest, db: AsyncSession = Depends(get_db)):
    results = await run_sherlock(body.username, db)
    return {"username": body.username, "results": results}


@router.get("/results")
async def get_results(username: str, db: AsyncSession = Depends(get_db)):
    result = await get_results_by_username(username=username, db=db)
    return {
        "username": username,
        "searches": [
            {
                "id": s.id,
                "created_at": s.created_at,
                "results": [{"site": r.site, "url": r.url} for r in s.results],
            }
            for s in result
        ],
    }
