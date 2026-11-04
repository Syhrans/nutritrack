
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# =====================================================
# DATABASE CONFIGURATION
# =====================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

IS_RENDER = os.getenv("RENDER", "").lower() == "true"

if IS_RENDER and not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Configure Neon PostgreSQL "
        "in Render Environment Variables."
    )

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./calorie_tracker.db"

# Support PostgreSQL URLs from common hosting providers.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

elif DATABASE_URL.startswith("postgresql"):
    if "sslmode=" not in DATABASE_URL:
        separator = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL += f"{separator}sslmode=require"

else:
    raise RuntimeError(
        "Unsupported DATABASE_URL database type."
    )


# =====================================================
# DATABASE ENGINE
# =====================================================

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
)


# =====================================================
# DATABASE SESSION
# =====================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# =====================================================
# SQLALCHEMY BASE
# =====================================================

Base = declarative_base()


# =====================================================
# DATABASE DEPENDENCY
# =====================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
