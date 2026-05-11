"""
Async MongoDB client – Motor singleton.

A single AsyncIOMotorClient is created on application startup (via FastAPI
lifespan) and torn down on shutdown.  Every part of the backend that needs
database access calls ``get_database()`` as a FastAPI dependency, which
returns the Motor database handle without creating a new connection.

Environment variables (backend/.env):
    DATABASE_URL      – MongoDB connection string (mongodb+srv://…)
    COMPLIANCE_DB_NAME – Target database name (default: constructai)
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# ── Module-level singleton ──────────────────────────────────────────────────────

_client: AsyncIOMotorClient | None = None  # type: ignore[type-arg]

# ── Connection lifecycle ────────────────────────────────────────────────────────


async def connect_to_mongo() -> None:
    """Open the Motor connection pool.  Called once on FastAPI startup."""
    global _client

    mongo_url: str = os.environ.get("DATABASE_URL", "")
    if not mongo_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it to backend/.env before starting the server."
        )

    logger.info("Connecting to MongoDB …")
    _client = AsyncIOMotorClient(
        mongo_url,
        # Motor / PyMongo tuning for a microservice workload
        maxPoolSize=20,
        minPoolSize=2,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=5_000,
        socketTimeoutMS=30_000,
    )

    # Verify the connection is reachable before accepting traffic.
    await _client.admin.command("ping")
    logger.info("MongoDB connection established.")


async def close_mongo_connection() -> None:
    """Close the Motor connection pool.  Called once on FastAPI shutdown."""
    global _client

    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed.")


# ── FastAPI dependency ──────────────────────────────────────────────────────────


async def get_database() -> AsyncGenerator[AsyncIOMotorDatabase, None]:  # type: ignore[type-arg]
    """
    FastAPI dependency that yields the Motor database handle.

    Usage in a router::

        @router.get("/example")
        async def example(db: Annotated[AsyncIOMotorDatabase, Depends(get_database)]):
            ...
    """
    if _client is None:
        raise RuntimeError(
            "MongoDB client is not initialised. "
            "Ensure connect_to_mongo() is called during application startup."
        )

    db_name: str = os.environ.get("COMPLIANCE_DB_NAME", "constructai")
    yield _client[db_name]
