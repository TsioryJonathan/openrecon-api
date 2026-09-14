from fastapi import APIRouter, HTTPException

from app.dorks import generate_dorks
from app.schemas import (
    DorkCategory,
    DorkGenerateRequest,
    DorkGenerateResponse,
    DorkItem,
    ErrorResponse,
)

router = APIRouter()


@router.post(
    "/generate",
    response_model=DorkGenerateResponse,
    summary="Generate Google dorks for a target",
    description=(
        "Generates a list of Google dork queries for a given target "
        "(username, email, domain, or real name). Each dork includes a copy-paste "
        "query and a direct Google search URL."
    ),
    responses={400: {"model": ErrorResponse, "description": "Empty target"}},
)
async def generate(body: DorkGenerateRequest):
    target = body.target.strip()
    if not target:
        raise HTTPException(status_code=400, detail="Target cannot be empty")

    categories = []
    total = 0
    for name, desc, dorks in generate_dorks(target):
        items = [DorkItem(title=t, query=q, url=u) for t, q, u in dorks]
        total += len(items)
        categories.append(DorkCategory(name=name, description=desc, dorks=items))

    return {"target": target, "total": total, "categories": categories}
