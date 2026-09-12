import uuid

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class Result(Base):
    __tablename__ = "results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    search_id = Column(
        String,
        ForeignKey("searches.id"),
        nullable=False,
    )

    search = relationship("Search", back_populates="results")

    site = Column(String, nullable=False)
    url = Column(String, nullable=False)
