import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


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

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id = Column(String, ForeignKey("findings.id"), nullable=False)
    source = Column(String, nullable=False)
    evidence_type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    meta = Column("metadata", JSONB, nullable=True)

    finding = relationship("Finding", back_populates="evidence")
