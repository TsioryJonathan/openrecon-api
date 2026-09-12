import uuid

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Search(Base):
    __tablename__ = "searches"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    results = relationship(
        "Result",
        back_populates="search",
        cascade="all, delete-orphan",
    )
