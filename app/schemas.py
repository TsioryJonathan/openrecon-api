from pydantic import BaseModel, Field


class ResultItem(BaseModel):
    site: str = Field(..., description="Platform name")
    url: str = Field(..., description="Profile URL found")


class SearchResponse(BaseModel):
    username: str = Field(..., description="Searched username")
    results: list[ResultItem] = Field(..., description="Found results")


class SearchResultEntry(BaseModel):
    id: str = Field(..., description="Unique search ID")
    created_at: str = Field(..., description="Search timestamp")
    results: list[ResultItem] = Field(..., description="Results from this search")


class GetResultsResponse(BaseModel):
    username: str = Field(..., description="Searched username")
    searches: list[SearchResultEntry] = Field(..., description="Search history")


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
