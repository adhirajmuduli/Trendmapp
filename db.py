import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, Float, String, Date, UniqueConstraint, ForeignKey, select
from dotenv import load_dotenv, find_dotenv

# ---------------------------------------------------------------------------
# Load environment variables -------------------------------------------------
# ---------------------------------------------------------------------------
load_dotenv(find_dotenv())
# Fallback: some users created 'oink.env'.
if "DATABASE_URL" not in os.environ:
    alt_path = Path(__file__).with_name("oink.env")
    if alt_path.exists():
        load_dotenv(alt_path)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set.")

# ---------------------------------------------------------------------------
# Build asyncpg-compatible URL & connection args ----------------------------
# ---------------------------------------------------------------------------
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

parsed = urlparse(DATABASE_URL)

# 1. Switch dialect driver to asyncpg
scheme_async = parsed.scheme.replace("postgresql", "postgresql+asyncpg", 1)

# 2. Remove unsupported query params (e.g. sslmode) for asyncpg
query_items = {k: v for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in ("sslmode", "channel_binding")}

ASYNC_DB_URL = urlunparse(parsed._replace(scheme=scheme_async, query=urlencode(query_items)))

# asyncpg requires ssl=True instead of sslmode=require. Always enforce SSL if
# the original URL had sslmode in its query string.
CONNECT_ARGS = {"ssl": True} if "sslmode" in parsed.query.lower() else {}

# ---------------------------------------------------------------------------
# SQLAlchemy base & engine ----------------------------------------------------
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    ASYNC_DB_URL,
    echo=True,  # Enable SQL logging for debugging
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,  # Enable connection health checks
    pool_recycle=300,  # Recycle connections after 5 minutes
    connect_args=CONNECT_ARGS,
)

AsyncSessionLocal = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

# ---------------------------------------------------------------------------
# ORM Models -----------------------------------------------------------------
# ---------------------------------------------------------------------------
class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String, default="Unnamed")


class Parameter(Base):
    __tablename__ = "parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    parameter_id: Mapped[int] = mapped_column(Integer, ForeignKey("parameters.id", ondelete="CASCADE"))
    sampled_at: Mapped[Date] = mapped_column(Date, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("station_id", "parameter_id", "sampled_at", name="uix_measurement_comb"),
    )


# ---------------------------------------------------------------------------
# Database Session Management -----------------------------------------------
# ---------------------------------------------------------------------------
@asynccontextmanager
async def get_db_session() -> AsyncGenerator:
    """Get a database session with proper cleanup and connection validation."""
    session = AsyncSessionLocal()
    try:
        # Validate the connection is still alive
        await session.execute(select(1))
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logging.error(f"Database error in session: {str(e)}", exc_info=True)
        raise e
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Utility to create all tables ----------------------------------------------
# ---------------------------------------------------------------------------
async def init_db() -> None:
    """Create tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all) 