import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.confidence import Confidence
from app.db.database import Base


class Finding(Base):
    """
    A Finding represents a piece of information discovered about a Target.

    Examples: a GitHub account, a subdomain, an IP address, a DNS record,
    an email address, an HTTP service, a repository.

    Fields:
    - type: canonical string identifying the kind of finding.
      Examples: "social_account", "subdomain", "ip_address", "dns_record",
                "email", "http_service", "repository".
    - value: the actual value (e.g. "https://github.com/john123", "api.example.com").
    - source: which module produced this finding (e.g. "sherlock", "dns", "rdap").
    - confidence: CONFIRMED / LIKELY / POSSIBLE (see app.core.confidence).
    - confidence_reason: short human-readable explanation of why this confidence
      level was assigned. Required — never store a confidence without a reason.
    - observed_at: when the finding was first observed (defaults to now).
    - target_id: FK to the Target this finding belongs to.
    - meta: arbitrary JSONB for module-specific data that doesn't fit the
      normalized fields. Do not query on this in application logic.
    """

    __tablename__ = "findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    source = Column(String, nullable=False)
    confidence = Column(String, nullable=False, default=Confidence.POSSIBLE)
    confidence_reason = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    target_id = Column(String, ForeignKey("targets.id"), nullable=False)
    meta = Column("metadata", JSONB, nullable=True)

    target = relationship("Target", back_populates="findings")
    evidence = relationship(
        "Evidence",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
