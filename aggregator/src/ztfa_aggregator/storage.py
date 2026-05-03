"""Persistence: SQLite/Postgres for round metadata + filesystem-or-S3 for blobs."""

from __future__ import annotations

import asyncio
import enum
import io
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class RoundState(str, enum.Enum):
    OPEN = "open"
    AGGREGATING = "aggregating"
    PROVING = "proving"
    AWAITING_CHAIN = "awaiting_chain"
    VERIFIED = "verified"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


class Round(Base):
    __tablename__ = "rounds"

    t: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String, default=RoundState.OPEN.value, nullable=False)
    deadline_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    h_agg_hex: Mapped[str | None] = mapped_column(String, nullable=True)
    aggregate_blob_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    commits: Mapped[list["ClientCommit"]] = relationship(back_populates="round")


class ClientCommit(Base):
    __tablename__ = "client_commits"
    __table_args__ = (
        UniqueConstraint("round_t", "client_id", name="uq_round_client"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_t: Mapped[int] = mapped_column(Integer, ForeignKey("rounds.t"), index=True)
    client_id: Mapped[int] = mapped_column(Integer, nullable=False)
    h_i_hex: Mapped[str] = mapped_column(String, nullable=False)
    blob_uri: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    round: Mapped[Round] = relationship(back_populates="commits")


class StorageBackend:
    """Object store abstraction. Local filesystem in dev; S3/MinIO in prod."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "ciphertexts").mkdir(exist_ok=True)
        (self.root / "aggregates").mkdir(exist_ok=True)

    async def put_ciphertext(self, round_t: int, client_id: int, data: bytes) -> str:
        path = self.root / "ciphertexts" / f"round_{round_t}_client_{client_id}.bin"
        await asyncio.to_thread(path.write_bytes, data)
        return str(path.resolve())

    async def get_ciphertext(self, uri: str) -> bytes:
        return await asyncio.to_thread(Path(uri).read_bytes)

    async def put_aggregate(self, round_t: int, data: bytes) -> str:
        path = self.root / "aggregates" / f"round_{round_t}.bin"
        await asyncio.to_thread(path.write_bytes, data)
        return str(path.resolve())

    async def get_aggregate(self, uri: str) -> bytes:
        return await asyncio.to_thread(Path(uri).read_bytes)


def make_engine(database_url: str):
    return create_async_engine(database_url, echo=False, future=True)


async def init_db(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def make_sessionmaker(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# Helper used by tests / dev: in-memory sqlite
def io_buffer(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)
