import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.Finding import Finding


class Target(Base):
    """
    A Target represents what is being investigated.

    Examples: a username, a domain, an IP address, an email, a URL.

    The `type` field is a free string (not an enum) to stay flexible as new
    target types are added. Canonical values: "username", "domain", "ip",
    "email", "url".

    `metadata` is a JSONB dict for any extra context attached at creation time
    (e.g. country hint, operator notes). It must never be used as a findings
    store — findings go in the Finding table.
    """

    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    findings: Mapped[list[Finding]] = relationship(
        "Finding",
        back_populates="target",
        cascade="all, delete-orphan",
    )
