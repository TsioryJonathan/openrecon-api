import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.orm import relationship

from app.db.database import Base


class InvestigationTarget(Base):
    """
    Join table between Investigation and Target.

    Using an explicit join model (rather than a plain secondary table) lets us
    attach metadata to the relationship — specifically:
    - role: optional label for why this target is in the investigation
      (e.g. "initial_target", "discovered_domain", "pivot").
    - added_at: when this target was linked to the investigation.

    A Target can belong to multiple Investigations (e.g. a domain found in two
    separate cases). An Investigation can have multiple Targets.
    """

    __tablename__ = "investigation_targets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    target_id = Column(String, ForeignKey("targets.id"), nullable=False)
    role = Column(String, nullable=True)  # e.g. "initial_target", "pivot"
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    investigation = relationship("Investigation", back_populates="targets")
    target = relationship("Target")
