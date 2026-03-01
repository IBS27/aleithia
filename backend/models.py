"""Database models for user profiles and query history."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer
from database import Base


class UserProfile(Base):
    """Store user's default settings."""

    __tablename__ = "user_profiles"

    clerk_user_id = Column(String(255), primary_key=True, index=True)
    business_type = Column(String(255), nullable=True)
    neighborhood = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QueryResult(Base):
    """Store past query results for user retrieval."""

    __tablename__ = "query_results"

    id = Column(Integer, primary_key=True, index=True)
    clerk_user_id = Column(String(255), index=True, nullable=False)
    business_type = Column(String(255), nullable=False)
    neighborhood = Column(String(255), nullable=False)
    query_text = Column(String(1000), nullable=False)
    result_summary = Column(String(5000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
