"""Project model."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from backend.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    repo_path = Column(String, nullable=False)
    repo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
