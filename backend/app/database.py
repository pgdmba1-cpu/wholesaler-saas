"""
Database setup.

Using SQLite for now — it's built into Python, needs no separate server
and no compiler (unlike psycopg2, which needs Postgres + build tools).
The data lives in a single file, wholesaler.db, created automatically
next to this code the first time the app runs.

Moving to real Postgres later is a one-line change: swap DATABASE_URL
for a postgres:// connection string once psycopg2 can install cleanly
(e.g. from a Mac/Linux machine, or after installing Microsoft C++
Build Tools on Windows).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./wholesaler.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: gives each request its own DB session, closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
