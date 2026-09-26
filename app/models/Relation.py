import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.Finding import Finding


# Canonical relation types.
# Add new types here when new correlation rules are implemented.
# Never use free-form strings in code — always reference these constants.
class RelationType:
    RESOLVES_TO = "RESOLVES_TO"  # domain/subdomain → IP address
    SUBDOMAIN_OF = "SUBDOMAIN_OF"  # subdomain → parent domain
    FOUND_ON = "FOUND_ON"  # username/email → social platform
    ASSOCIATED_WITH = "ASSOCIATED_WITH"  # generic weak association
    SHARES_IP = "SHARES_IP"  # two domains resolve to same IP
    HAS_DNS_RECORD = "HAS_DNS_RECORD"  # domain → DNS record finding


class Relation(Base):
    """
    A directed, typed edge between two Findings.

    Represents a meaningful relationship discovered by the correlation engine.
    Every Relation must have:
    - A source and target Finding (both must exist in the DB).
    - A relation_type from RelationType constants.
    - A confidence level (CONFIRMED / LIKELY / POSSIBLE).
    - A reason explaining why this relation was created.

    Relations are directional:
        source_finding → [relation_type] → target_finding
    Example:
        "example.com A 1.2.3.4" → RESOLVES_TO → "1.2.3.4"

    A Relation is never invented. It is always derived from actual Findings
    and their normalized values. The correlator must be able to explain
    every relation it creates in plain text (stored in `reason`).

    meta: JSONB for storing extra context (e.g. which rule matched,
    intermediate values used in the correlation).
    """

    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_finding_id: Mapped[str] = mapped_column(
        String, ForeignKey("findings.id"), nullable=False
    )
    target_finding_id: Mapped[str] = mapped_column(
        String, ForeignKey("findings.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    source_finding: Mapped[Finding] = relationship("Finding", foreign_keys=[source_finding_id])
    target_finding: Mapped[Finding] = relationship("Finding", foreign_keys=[target_finding_id])
