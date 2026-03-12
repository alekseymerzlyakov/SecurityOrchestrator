"""Prompt model."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from backend.database import Base


class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=True)  # architecture, xss, auth, dependencies, general
    content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
