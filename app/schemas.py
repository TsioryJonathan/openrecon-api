from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sherlock (existing — do not modify)
# ---------------------------------------------------------------------------


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


# --- Dork (existing — do not modify) ---


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


# --- EXIF (existing — do not modify) ---


class ExifResponse(BaseModel):
    filename: str = Field(..., description="Original filename")
    has_gps: bool = Field(..., description="Whether GPS coordinates were found")
    gps: dict | None = Field(None, description="GPS data (lat, lon, altitude)")
    device: dict | None = Field(None, description="Device info (make, model)")
    lens: str | None = Field(None, description="Lens model")
    camera_settings: dict | None = Field(
        None, description="Camera settings (focal length, aperture, ISO, etc.)"
    )
    image: dict | None = Field(None, description="Image info (dimensions, color space)")
    flash: str | None = Field(None, description="Flash info")
    white_balance: str | None = Field(None, description="White balance setting")
    scene_type: str | None = Field(None, description="Scene type")
    datetime: str | None = Field(None, description="Original capture date/time")
    software: str | None = Field(None, description="Software used to process the image")
    artist: str | None = Field(None, description="Artist/owner name")
    copyright: str | None = Field(None, description="Copyright information")


# --- Recon (existing — do not modify) ---


class ReconResponse(BaseModel):
    query: str = Field(..., description="Original query")
    type: str = Field(..., description="Type of query: 'ip' or 'domain'")
    data: dict = Field(..., description="Recon results")


# ---------------------------------------------------------------------------
# Scan — new
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    target_type: str = Field(
        ...,
        description="Type of the target. Currently supported: 'username'.",
        examples=["username"],
    )
    target_value: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="The value to investigate (e.g. a username, domain, or IP).",
        examples=["john123"],
    )
    sites: list[str] = Field(
        default_factory=list,
        description=(
            "For username scans: restrict to these Sherlock site names. "
            "Omit or pass an empty list to scan all supported sites."
        ),
        examples=[["GitHub", "Reddit", "Twitter"]],
    )


class ScanEvidenceItem(BaseModel):
    id: str = Field(..., description="Evidence ID")
    source: str = Field(..., description="Module that produced this evidence")
    evidence_type: str = Field(..., description="Kind of evidence (e.g. 'url')")
    value: str = Field(..., description="Raw evidence value")
    observed_at: str = Field(..., description="ISO timestamp")


class ScanFindingItem(BaseModel):
    id: str = Field(..., description="Finding ID")
    type: str = Field(..., description="Finding type (e.g. 'social_account')")
    value: str = Field(..., description="Finding value (e.g. a profile URL)")
    source: str = Field(..., description="Module that produced this finding")
    confidence: str = Field(..., description="CONFIRMED / LIKELY / POSSIBLE")
    confidence_reason: str = Field(..., description="Why this confidence was assigned")
    observed_at: str = Field(..., description="ISO timestamp")
    evidence: list[ScanEvidenceItem] = Field(
        default_factory=list,
        description="Evidence backing this finding",
    )


class ScanTargetItem(BaseModel):
    id: str = Field(..., description="Target ID")
    type: str = Field(..., description="Target type")
    value: str = Field(..., description="Target value")
    created_at: str = Field(..., description="ISO timestamp")


class ScanResponse(BaseModel):
    target: ScanTargetItem = Field(..., description="The investigated target")
    finding_count: int = Field(..., description="Total findings stored")
    evidence_count: int = Field(..., description="Total evidence stored")
    modules_run: list[str] = Field(..., description="Modules that were executed")
    findings: list[ScanFindingItem] = Field(..., description="All findings from this scan")
    errors: list[str] = Field(
        default_factory=list,
        description="Errors encountered during the scan (partial results possible)",
    )
