from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SHERLOCK_SITES
from app.db.database import get_db
from app.services.sherlock import get_results_by_username, run_sherlock

router = APIRouter()


class SearchRequest(BaseModel):
    username: str
    sites: list[str]


@router.post("/search")
async def search_username(body: SearchRequest, db: AsyncSession = Depends(get_db)):
    if len(body.sites) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 sites allowed")

    invalid = [s for s in body.sites if s not in SHERLOCK_SITES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported sites: {', '.join(invalid)}",
        )

    results = await run_sherlock(body.username, body.sites, db)
    return {"username": body.username, "results": results}


@router.get("/results")
async def get_results(username: str, db: AsyncSession = Depends(get_db)):
    result = await get_results_by_username(username=username, db=db)
    if isinstance(result, dict):
        return result
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
