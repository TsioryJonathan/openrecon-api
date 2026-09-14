from pydantic import BaseModel, Field


class ResultItem(BaseModel):
    site: str = Field(..., description="Nom de la plateforme")
    url: str = Field(..., description="URL du profil trouvé")


class SearchResponse(BaseModel):
    username: str = Field(..., description="Nom d'utilisateur recherché")
    results: list[ResultItem] = Field(..., description="Résultats trouvés")


class SearchResultEntry(BaseModel):
    id: str = Field(..., description="ID unique de la recherche")
    created_at: str = Field(..., description="Date de la recherche")
    results: list[ResultItem] = Field(..., description="Résultats de cette recherche")


class GetResultsResponse(BaseModel):
    username: str = Field(..., description="Nom d'utilisateur recherché")
    searches: list[SearchResultEntry] = Field(..., description="Historique des recherches")


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
