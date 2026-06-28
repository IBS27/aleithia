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


def _migrate_legacy_user_id_columns() -> None:
    """Rename user identity columns left over from the old auth integration."""
    targets = ("user_profiles", "query_results")

    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        for table_name in targets:
            if table_name not in existing_tables:
                continue

            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "clerk_user_id" in columns and "user_id" not in columns:
                conn.execute(text(f"ALTER TABLE {table_name} RENAME COLUMN clerk_user_id TO user_id"))
            elif "clerk_user_id" in columns and "user_id" in columns:
                conn.execute(
                    text(
                        f"UPDATE {table_name} "
                        "SET user_id = clerk_user_id "
                        "WHERE user_id IS NULL OR user_id = ''"
                    )
                )


def get_db() -> Session:
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    _migrate_legacy_user_id_columns()
    Base.metadata.create_all(bind=engine)
