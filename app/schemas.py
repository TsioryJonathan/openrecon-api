from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sherlock (existing — do not modify)
# ---------------------------------------------------------------------------


class ResultItem(BaseModel):
    site: str = Field(..., description="Platform name")
    url: str = Field(..., description="Profile URL found")


class SearchResponse(BaseModel):
    username: str
    results: list[ResultItem]


class SearchResultEntry(BaseModel):
    id: str
    created_at: str
    results: list[ResultItem]


class GetResultsResponse(BaseModel):
    username: str
    searches: list[SearchResultEntry]


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class CategorySites(BaseModel):
    name: str
    sites: list[str]


class SitesResponse(BaseModel):
    categories: list[CategorySites]
    total: int


# --- Dork ---


class DorkItem(BaseModel):
    title: str
    query: str
    url: str


class DorkCategory(BaseModel):
    name: str
    description: str
    dorks: list[DorkItem]


class DorkGenerateRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=64, examples=["john_doe"])


class DorkGenerateResponse(BaseModel):
    target: str
    total: int
    categories: list[DorkCategory]


# --- EXIF ---


class ExifResponse(BaseModel):
    filename: str
    has_gps: bool
    gps: dict | None = None
    device: dict | None = None
    lens: str | None = None
    camera_settings: dict | None = None
    image: dict | None = None
    flash: str | None = None
    white_balance: str | None = None
    scene_type: str | None = None
    datetime: str | None = None
    software: str | None = None
    artist: str | None = None
    copyright: str | None = None


# --- Recon ---


class ReconResponse(BaseModel):
    query: str
    type: str
    data: dict


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    target_type: str = Field(
        ...,
        description="Type of the target. Supported: 'username', 'domain'.",
        examples=["username", "domain"],
    )
    target_value: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="The value to investigate.",
        examples=["john123", "example.com"],
    )
    options: dict = Field(
        default_factory=dict,
        description=(
            "Module-specific options.\n"
            'username → {"sites": ["GitHub", "Reddit"]}\n'
            "domain   → no options currently used"
        ),
        examples=[{"sites": ["GitHub", "Reddit"]}, {}],
    )


class ScanEvidenceItem(BaseModel):
    id: str
    source: str
    evidence_type: str
    value: str
    observed_at: str


class ScanFindingItem(BaseModel):
    id: str
    type: str
    value: str
    source: str
    confidence: str
    confidence_reason: str
    observed_at: str
    evidence: list[ScanEvidenceItem] = Field(default_factory=list)


class ScanTargetItem(BaseModel):
    id: str
    type: str
    value: str
    created_at: str


class ScanResponse(BaseModel):
    target: ScanTargetItem
    finding_count: int
    evidence_count: int
    modules_run: list[str]
    findings: list[ScanFindingItem]
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Investigation
# ---------------------------------------------------------------------------


class InvestigationCreateRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Short label for the investigation.",
        examples=["john123 OSINT"],
    )
    description: str | None = Field(None, description="Optional free-text notes.")


class InvestigationAddTargetRequest(BaseModel):
    target_type: str = Field(..., description="Type of the target.", examples=["username"])
    target_value: str = Field(..., min_length=1, max_length=253, examples=["john123"])
    role: str | None = Field(
        None,
        description="Optional role label.",
        examples=["initial_target", "pivot", "discovered_domain"],
    )


class InvestigationScanRequest(BaseModel):
    target_type: str = Field(
        ...,
        description="Type of the target. Supported: 'username', 'domain'.",
        examples=["username", "domain"],
    )
    target_value: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="The value to investigate.",
        examples=["john123"],
    )
    options: dict = Field(
        default_factory=dict,
        description="Module-specific options (same as POST /api/scan).",
        examples=[{"sites": ["GitHub"]}, {}],
    )
    role: str | None = Field(
        None,
        description=(
            "Role label for the target link in this investigation. "
            "Examples: 'initial_target', 'pivot', 'discovered_domain'."
        ),
        examples=["initial_target"],
    )


class InvestigationTargetItem(BaseModel):
    id: str
    type: str
    value: str
    role: str | None
    added_at: str
    finding_count: int


class InvestigationSummaryResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_at: str
    updated_at: str
    target_count: int
    finding_count: int
    evidence_count: int
    targets: list[InvestigationTargetItem] = Field(default_factory=list)


class InvestigationListItem(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_at: str
    updated_at: str


class InvestigationListResponse(BaseModel):
    total: int
    investigations: list[InvestigationListItem]


class InvestigationScanResponse(BaseModel):
    """Response for POST /api/investigations/{id}/scan."""

    scan: ScanResponse
    investigation: InvestigationSummaryResponse
