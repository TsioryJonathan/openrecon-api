from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SHERLOCK_SITES
from app.db.database import get_db
from app.schemas import ErrorResponse, GetResultsResponse, MessageResponse, SearchResponse
from app.services.sherlock import get_results_by_username, run_sherlock

router = APIRouter()


class SearchRequest(BaseModel):
    username: str = Field(..., description="Nom d'utilisateur à rechercher", examples=["john_doe"])
    sites: list[str] = Field(
        ...,
        description="Liste des plateformes à scanner (max 50). "
        "Utilise les noms exacts de sherlock (ex: GitHub, Twitter, Instagram).",
        examples=[["GitHub", "Twitter", "Instagram"]],
        max_length=50,
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Lancer une recherche OSINT",
    description=(
        "Lance une recherche sherlock sur les plateformes spécifiées. "
        "Le nom d'utilisateur est vérifié sur chaque site de la liste. "
        "Les résultats sont sauvegardés en base pour consultation ultérieure."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Sites invalides ou dépassement de la limite"},
    },
)
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


@router.get(
    "/results",
    response_model=GetResultsResponse | MessageResponse,
    summary="Récupérer les résultats d'une recherche",
    description=(
        "Retourne l'historique de toutes les recherches effectuées pour un nom d'utilisateur donné. "
        "Chaque recherche contient la liste des résultats trouvés."
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
