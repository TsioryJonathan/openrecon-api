import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.Finding import Finding


class Evidence(Base):
    """
    Evidence justifies a Finding.

    Every Finding should have at least one piece of Evidence. A Finding without
    Evidence is a claim without a source — avoid it.

    Fields:
    - finding_id: FK to the Finding this evidence supports.
    - source: which tool or service produced this evidence
      (e.g. "sherlock", "dns", "crt.sh", "rdap", "exiftool").
    - evidence_type: the kind of data this evidence contains.
      Examples: "url", "dns_record", "http_response", "whois_field",
                "certificate_entry", "file_metadata".
    - value: the raw value of the evidence
      (e.g. "https://github.com/john123", "api.example.com A 1.2.3.4").
    - observed_at: when the evidence was collected (defaults to now).
    - meta: arbitrary JSONB for raw response data, HTTP status codes, etc.
      Store whatever the module returned so it can be audited later.
    """

    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id: Mapped[str] = mapped_column(String, ForeignKey("findings.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    finding: Mapped[Finding] = relationship("Finding", back_populates="evidence")
