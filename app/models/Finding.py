import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.confidence import Confidence
from app.db.database import Base

if TYPE_CHECKING:
    from app.models.Evidence import Evidence
    from app.models.Target import Target


class Finding(Base):
    """
    A Finding represents a piece of information discovered about a Target.

    Examples: a GitHub account, a subdomain, an IP address, a DNS record,
    an email address, an HTTP service, a repository.

    Fields:
    - type: canonical string identifying the kind of finding.
      Examples: "social_account", "subdomain", "ip_address", "dns_record",
                "email", "http_service", "repository".
    - value: the original value as returned by the module (preserved as-is).
    - normalized_value: canonical form of value used for deduplication.
      Computed by app.core.normalizer.normalize_finding_value().
      Not shown to users; used only as a dedup key.
    - source: which module produced this finding (e.g. "sherlock", "dns").
    - confidence: CONFIRMED / LIKELY / POSSIBLE (see app.core.confidence).
    - confidence_reason: short human-readable explanation of why this confidence
      level was assigned. Required — never store a confidence without a reason.
    - observed_at: when the finding was first observed (defaults to now).
    - target_id: FK to the Target this finding belongs to.
    - meta: arbitrary JSONB for module-specific data. Do not query on this.

    Deduplication key: (target_id, type, normalized_value) — enforced via
    a DB index. The deduplicator in app.core.deduplicator checks this before
    insertion; the index makes the lookup fast.
    """

    __tablename__ = "findings"
    __table_args__ = (
        # Speeds up dedup lookups — not a unique constraint because the same
        # normalized value can legitimately come from different modules/runs.
        Index("ix_findings_dedup", "target_id", "type", "normalized_value"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    normalized_value: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[str] = mapped_column(String, nullable=False, default=Confidence.POSSIBLE)
    confidence_reason: Mapped[str] = mapped_column(String, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String, ForeignKey("targets.id"), nullable=False)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    target: Mapped[Target] = relationship("Target", back_populates="findings")
    evidence: Mapped[list[Evidence]] = relationship(
        "Evidence",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
