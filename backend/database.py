"""Database setup and session management."""

import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    _ensure_user_profiles_columns()


def _ensure_user_profiles_columns():
    """Best-effort migration for existing user_profiles tables."""
    inspector = inspect(engine)
    if "user_profiles" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("user_profiles")}
    statements: list[str] = []

    if "risk_tolerance" not in existing:
        statements.append("ALTER TABLE user_profiles ADD COLUMN risk_tolerance VARCHAR(50) NOT NULL DEFAULT 'medium'")
    if not statements:
        return

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
