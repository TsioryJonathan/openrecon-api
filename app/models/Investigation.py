import uuid

from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.orm import relationship

from app.db.database import Base


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

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # many-to-many via InvestigationTarget join table
    targets = relationship(
        "InvestigationTarget",
        back_populates="investigation",
        cascade="all, delete-orphan",
    )
