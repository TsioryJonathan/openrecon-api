from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sherlock (existing — do not modify)
# ---------------------------------------------------------------------------


class ResultItem(BaseModel):
    site: str
    url: str


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
    target_type: str = Field(..., examples=["username", "domain"])
    target_value: str = Field(..., min_length=1, max_length=253, examples=["john123"])
    options: dict = Field(default_factory=dict, examples=[{"sites": ["GitHub"]}, {}])


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
    name: str = Field(..., min_length=1, max_length=200, examples=["john123 OSINT"])
    description: str | None = None


class InvestigationAddTargetRequest(BaseModel):
    target_type: str = Field(..., examples=["username"])
    target_value: str = Field(..., min_length=1, max_length=253, examples=["john123"])
    role: str | None = Field(None, examples=["initial_target"])


class InvestigationScanRequest(BaseModel):
    target_type: str = Field(..., examples=["username"])
    target_value: str = Field(..., min_length=1, max_length=253, examples=["john123"])
    options: dict = Field(default_factory=dict, examples=[{"sites": ["GitHub"]}, {}])
    role: str | None = Field(None, examples=["initial_target"])


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
    scan: ScanResponse
    investigation: InvestigationSummaryResponse


class InvestigationTargetFindingsResponse(BaseModel):
    target_id: str
    finding_count: int
    findings: list[ScanFindingItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------


class RelationItem(BaseModel):
    id: str
    source_finding_id: str
    target_finding_id: str
    relation_type: str
    confidence: str
    reason: str
    created_at: str

    # Enriched (optional) finding details for the graph. Set by
    # `build_relation_items` in app/services/correlation.py. `None` when the
    # referenced finding is missing (orphaned data).
    source_finding_type: str | None = None
    source_finding_value: str | None = None
    source_finding_target_id: str | None = None
    target_finding_type: str | None = None
    target_finding_value: str | None = None
    target_finding_target_id: str | None = None


class CorrelationResponse(BaseModel):
    investigation_id: str
    relations_created: int
    relations_skipped: int
    errors: list[str] = Field(default_factory=list)
    relations: list[RelationItem] = Field(default_factory=list)


class InvestigationRelationsResponse(BaseModel):
    investigation_id: str
    relation_count: int
    relations: list[RelationItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class ReportResponse(BaseModel):
    investigation: dict
    generated_at: str
    targets: list[dict]
    relations: list[dict]
    timeline: list[dict]
    sources: list[str]
    stats: dict


# ---------------------------------------------------------------------------
# Adaptive scan
# ---------------------------------------------------------------------------


class AdaptiveLeadItem(BaseModel):
    target_type: str
    target_value: str
    rule: str = Field(..., description="Which extraction rule produced this lead.")
    source_finding_id: str


class AdaptiveHopItem(BaseModel):
    depth: int
    target_type: str
    target_value: str
    finding_count: int
    evidence_count: int
    modules_run: list[str]
    errors: list[str] = Field(default_factory=list)
    leads_extracted: list[AdaptiveLeadItem] = Field(default_factory=list)
    source_lead: AdaptiveLeadItem | None = None


class AdaptiveTargetItem(BaseModel):
    type: str
    value: str


class AdaptiveScanResponse(BaseModel):
    investigation_id: str
    max_depth: int = Field(..., description="Maximum hops configured for this run.")
    hop_count: int = Field(..., description="Total number of hops executed.")
    targets_scanned: list[AdaptiveTargetItem] = Field(
        ..., description="All (type, value) pairs scanned in this run."
    )
    total_finding_count: int
    total_evidence_count: int
    hops: list[AdaptiveHopItem] = Field(..., description="Per-hop results, depth 0 first.")
    leads_skipped: list[dict] = Field(
        default_factory=list,
        description="Leads not scanned (out of scope, deduped, unsupported type, depth exceeded).",
    )
    errors: list[str] = Field(default_factory=list)
    investigation: InvestigationSummaryResponse
