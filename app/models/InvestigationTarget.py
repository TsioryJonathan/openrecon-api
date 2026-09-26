import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.Investigation import Investigation
    from app.models.Target import Target


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

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    investigation_id: Mapped[str] = mapped_column(
        String, ForeignKey("investigations.id"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String, ForeignKey("targets.id"), nullable=False)
    role: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # e.g. "initial_target", "pivot"
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    investigation: Mapped[Investigation] = relationship("Investigation", back_populates="targets")
    target: Mapped[Target] = relationship("Target")
