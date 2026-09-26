import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.InvestigationTarget import InvestigationTarget


class Investigation(Base):
    """
    An Investigation groups one or more Targets under a named context.

    Instead of treating every scan as independent, an Investigation lets the
    operator track related targets together:
        Investigation "john123 OSINT"
            ├── Target: username / john123
            ├── Target: domain / example.com
            └── Target: ip / 1.2.3.4

    All Findings for each Target are reachable via target.findings.

    Fields:
    - name: short human-readable label ("john123 OSINT", "Acme Corp audit").
    - description: optional free-text notes about the investigation.
    - created_at: when the investigation was opened.
    - updated_at: last time a target was added or a scan run.
    - status: open | closed. Closed investigations are read-only by convention
      (not enforced at DB level — enforced in the service layer).
    """

    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # many-to-many via InvestigationTarget join table
    targets: Mapped[list[InvestigationTarget]] = relationship(
        "InvestigationTarget",
        back_populates="investigation",
        cascade="all, delete-orphan",
    )
