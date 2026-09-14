from fastapi import APIRouter, HTTPException

from app.schemas import ErrorResponse, ReconResponse
from app.services.recon import recon

router = APIRouter()


@router.get(
    "",
    response_model=ReconResponse,
    summary="Recon an IP address or domain",
    description=(
        "Accepts an IPv4/IPv6 address or a domain name. For an IP, returns "
        "geolocation, ISP, ASN, and proxy status. For a domain, returns registrar, "
        "creation/expiry dates, nameservers, DNS records, and subdomains."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query"},
        502: {"model": ErrorResponse, "description": "Upstream service error"},
    },
)
async def get_recon(query: str):
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        query_type, data = await recon(query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Recon failed: {e}")

    return {"query": query, "type": query_type, "data": data}
