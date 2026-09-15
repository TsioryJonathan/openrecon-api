import uuid

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


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

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    meta = Column("metadata", JSONB, nullable=True)

    findings = relationship(
        "Finding",
        back_populates="target",
        cascade="all, delete-orphan",
    )
