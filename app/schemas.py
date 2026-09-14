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


class CategorySites(BaseModel):
    name: str = Field(..., description="Category name")
    sites: list[str] = Field(..., description="List of site names in this category")


class SitesResponse(BaseModel):
    categories: list[CategorySites] = Field(..., description="Sites grouped by category")
    total: int = Field(..., description="Total number of supported sites")


# --- Dork ---

class DorkItem(BaseModel):
    title: str = Field(..., description="Human-readable name for this dork")
    query: str = Field(..., description="The Google dork query string")
    url: str = Field(..., description="Direct Google search URL")


class DorkCategory(BaseModel):
    name: str = Field(..., description="Category name")
    description: str = Field(..., description="What this category covers")
    dorks: list[DorkItem] = Field(..., description="List of dorks in this category")


class DorkGenerateRequest(BaseModel):
    target: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Target to generate dorks for (username, email, domain, or name)",
        examples=["john_doe"],
    )


class DorkGenerateResponse(BaseModel):
    target: str = Field(..., description="The target that was used")
    total: int = Field(..., description="Total number of dorks generated")
    categories: list[DorkCategory] = Field(..., description="Dorks grouped by category")


# --- EXIF ---

class ExifResponse(BaseModel):
    filename: str = Field(..., description="Original filename")
    has_gps: bool = Field(..., description="Whether GPS coordinates were found")
    gps: dict | None = Field(None, description="GPS data (lat, lon, altitude)")
    device: dict | None = Field(None, description="Device info (make, model)")
    datetime: str | None = Field(None, description="Original capture date/time")
    software: str | None = Field(None, description="Software used to process the image")
    artist: str | None = Field(None, description="Artist/owner name")
    copyright: str | None = Field(None, description="Copyright information")


# --- Recon ---

class ReconResponse(BaseModel):
    query: str = Field(..., description="Original query")
    type: str = Field(..., description="Type of query: 'ip' or 'domain'")
    data: dict = Field(..., description="Recon results")
