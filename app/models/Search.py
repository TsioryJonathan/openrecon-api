import uuid

from sqlalchemy.orm import relationship

from app.db.database import Base
from sqlalchemy import Column, String, DateTime


class Search(Base):
    __tablename__ = "searches"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String)
    created_at = Column(DateTime)
    results = relationship("Result", back_populates="search")
