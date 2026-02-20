"""Database storage configuration."""

import os

from sqlmodel import SQLModel, create_engine

# Get database URL from environment -- no fallback
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is required but not set. "
        "Set it to your PostgreSQL connection string (e.g., postgresql://user:pass@localhost/dbname)"
    )

# Create engine with appropriate settings
connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)


def create_db_and_tables() -> None:
    """Create all database tables."""
    SQLModel.metadata.create_all(engine)
