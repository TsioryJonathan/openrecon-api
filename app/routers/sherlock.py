from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import SHERLOCK_CATEGORIES
from app.constants import SHERLOCK_SITES
from app.db.database import get_db
from app.schemas import (
    ErrorResponse,
    GetResultsResponse,
    MessageResponse,
    SearchResponse,
    SitesResponse,
)
from app.services.sherlock import get_results_by_username, run_sherlock

router = APIRouter()


@router.get(
    "/sites",
    response_model=SitesResponse,
    summary="List all supported sites",
    description=(
        "Returns the full list of platforms supported by sherlock, "
        "grouped by category. Use these names in the search endpoint."
    ),
)
async def get_sites():
    categories = [{"name": name, "sites": sites} for name, sites in SHERLOCK_CATEGORIES.items()]
    total = sum(len(c["sites"]) for c in categories)
    return {"categories": categories, "total": total}


class SearchRequest(BaseModel):
    username: str = Field(..., description="Username to search for", examples=["john_doe"])
    sites: list[str] = Field(
        ...,
        description="List of platforms to scan. "
        "Use exact sherlock site names (e.g. GitHub, Twitter, Instagram).",
        examples=[["GitHub", "Twitter", "Instagram"]],
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Launch an OSINT search",
    description=(
        "Runs a sherlock scan on the specified platforms. "
        "The username is checked on each site in the list. "
        "Results are saved to the database for later retrieval."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported sites"},
    },
)
async def search_username(body: SearchRequest, db: AsyncSession = Depends(get_db)):
    invalid = [s for s in body.sites if s not in SHERLOCK_SITES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported sites: {', '.join(invalid)}",
        )

    results = await run_sherlock(body.username, body.sites, db)
    return {"username": body.username, "results": results}


@router.get(
    "/results",
    response_model=GetResultsResponse | MessageResponse,
    summary="Retrieve search results",
    description=(
        "Returns the history of all searches performed for a given username. "
        "Each search includes the list of results found."
    ),
)
async def get_results(username: str, db: AsyncSession = Depends(get_db)):
    result = await get_results_by_username(username=username, db=db)
    if isinstance(result, dict):
        return result
    return {
        "username": username,
        "searches": [
            {
                "id": s.id,
                "created_at": str(s.created_at),
                "results": [{"site": r.site, "url": r.url} for r in s.results],
            }
            for s in result
        ],
    }
