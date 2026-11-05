"""
Database Models and Asynchronous SQLite Persistence Layer.

Provides SQLAlchemy 2.0 async models for Users, HostedBots, and BotLogEntries,
together with database lifecycle and CRUD helper functions.
"""

from __future__ import annotations

import enum
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.core.config import settings


class BotStatus(str, enum.Enum):
    """Lifecycle status values for hosted bots."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CRASHED = "CRASHED"
    ERROR = "ERROR"


class Base(DeclarativeBase):
    """Base declarative class for all database models."""
    pass


class User(Base):
    """Telegram user model authorized to host and manage bots."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_bots: Mapped[int] = mapped_column(Integer, default=settings.MAX_BOTS_PER_USER, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    bots: Mapped[List["HostedBot"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} is_admin={self.is_admin}>"


class HostedBot(Base):
    """Hosted Telegram bot metadata, process configuration, and current status."""

    __tablename__ = "hosted_bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[BotStatus] = mapped_column(
        SAEnum(BotStatus, native_enum=False, length=20),
        default=BotStatus.STOPPED,
        nullable=False,
        index=True,
    )
    pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runtime_type: Mapped[str] = mapped_column(String(50), default="python", nullable=False)
    entry_point: Mapped[str] = mapped_column(String(255), default="main.py", nullable=False)
    restart_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_restart: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    env_vars: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="bots", lazy="selectin")
    logs: Mapped[List["BotLogEntry"]] = relationship(
        back_populates="bot",
        cascade="all, delete-orphan",
        order_by="BotLogEntry.id.desc()",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<HostedBot id={self.id} name={self.name!r} status={self.status.value} pid={self.pid}>"


class BotLogEntry(Base):
    """Persisted log line produced by a child bot process or supervisor event."""

    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("hosted_bots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
    stream: Mapped[str] = mapped_column(String(20), default="stdout", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    bot: Mapped["HostedBot"] = relationship(back_populates="logs")

    def __repr__(self) -> str:
        return f"<BotLogEntry bot_id={self.bot_id} stream={self.stream!r} ts={self.timestamp}>"


# Engine and session factory globals
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Retrieve or create the global async database engine."""
    global _engine
    if _engine is None:
        url = database_url or settings.DATABASE_URL
        # Ensure parent directory exists for SQLite files
        if url.startswith("sqlite+aiosqlite:///"):
            raw_path = url.replace("sqlite+aiosqlite:///", "")
            # Handle relative vs absolute paths
            db_path = Path(raw_path)
            if not db_path.is_absolute():
                db_path = settings.BASE_DIR / db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            # Reconstruct absolute URL
            url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

        _engine = create_async_engine(
            url,
            echo=False,
            future=True,
        )

        from sqlalchemy import event

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
            except Exception:
                pass
    return _engine


def get_sessionmaker(database_url: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    """Retrieve or initialize the async sessionmaker."""
    global _sessionmaker
    if _sessionmaker is None:
        engine = get_engine(database_url)
        _sessionmaker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _sessionmaker


@asynccontextmanager
async def get_session(database_url: Optional[str] = None) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async transactional database session context."""
    factory = get_sessionmaker(database_url)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(database_url: Optional[str] = None) -> None:
    """Initialize database tables and schema."""
    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the database engine and clean up connection pools."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


# ---------------------------------------------------------------------------
# CRUD Helper Functions
# ---------------------------------------------------------------------------

async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
    is_admin: bool = False,
) -> User:
    """Fetch existing user by Telegram ID or create a new user record."""
    stmt = select(User).where(User.id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        # Check if the telegram_id is in ADMIN_IDS configuration
        admin_flag = is_admin or (telegram_id in settings.ADMIN_IDS)
        user = User(
            id=telegram_id,
            username=username,
            full_name=full_name,
            is_admin=admin_flag,
            max_bots=settings.MAX_BOTS_PER_USER,
        )
        session.add(user)
        await session.flush()
    else:
        # Update user attributes if changed
        updated = False
        if username is not None and user.username != username:
            user.username = username
            updated = True
        if full_name is not None and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        if telegram_id in settings.ADMIN_IDS and not user.is_admin:
            user.is_admin = True
            updated = True
        if updated:
            user.updated_at = datetime.now(timezone.utc)
            await session.flush()

    return user


async def get_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    """Retrieve a user by their Telegram ID."""
    stmt = select(User).where(User.id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_user_max_bots(
    session: AsyncSession, telegram_id: int, max_bots: int
) -> Optional[User]:
    """Update the maximum number of bots a user is permitted to host."""
    user = await get_user(session, telegram_id)
    if user:
        user.max_bots = max_bots
        user.updated_at = datetime.now(timezone.utc)
        await session.flush()
    return user


async def create_hosted_bot(
    session: AsyncSession,
    user_id: int,
    name: str,
    runtime_type: str = "python",
    entry_point: str = "main.py",
    token: Optional[str] = None,
    auto_restart: bool = True,
    env_vars: Optional[Dict[str, Any]] = None,
) -> HostedBot:
    """Register a new hosted bot record."""
    bot = HostedBot(
        user_id=user_id,
        name=name,
        runtime_type=runtime_type,
        entry_point=entry_point,
        token=token,
        status=BotStatus.STOPPED,
        auto_restart=auto_restart,
        env_vars=env_vars or {},
    )
    session.add(bot)
    await session.flush()
    return bot


async def get_bot(session: AsyncSession, bot_id: int) -> Optional[HostedBot]:
    """Retrieve a hosted bot by its primary key ID."""
    stmt = select(HostedBot).where(HostedBot.id == bot_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_bots(session: AsyncSession, user_id: int) -> List[HostedBot]:
    """Retrieve all hosted bots belonging to a specific user."""
    stmt = select(HostedBot).where(HostedBot.user_id == user_id).order_by(HostedBot.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_bots(session: AsyncSession) -> List[HostedBot]:
    """Retrieve all hosted bots across the entire system."""
    stmt = select(HostedBot).order_by(HostedBot.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_bot_status(
    session: AsyncSession,
    bot_id: int,
    status: BotStatus,
    pid: Optional[int] = None,
) -> Optional[HostedBot]:
    """Update status and active PID for a hosted bot."""
    bot = await get_bot(session, bot_id)
    if bot:
        bot.status = status
        bot.pid = pid
        bot.updated_at = datetime.now(timezone.utc)
        await session.flush()
    return bot


async def update_bot_restart_count(
    session: AsyncSession,
    bot_id: int,
    count: int,
) -> Optional[HostedBot]:
    """Update the auto-restart counter for a hosted bot."""
    bot = await get_bot(session, bot_id)
    if bot:
        bot.restart_count = count
        bot.updated_at = datetime.now(timezone.utc)
        await session.flush()
    return bot


async def update_bot_entry_point(
    session: AsyncSession,
    bot_id: int,
    entry_point: str,
) -> Optional[HostedBot]:
    """Update entry point file path for a hosted bot."""
    bot = await get_bot(session, bot_id)
    if bot:
        bot.entry_point = entry_point
        bot.updated_at = datetime.now(timezone.utc)
        await session.flush()
    return bot


async def update_bot_env_vars(
    session: AsyncSession,
    bot_id: int,
    env_vars: Dict[str, Any],
) -> Optional[HostedBot]:
    """Update custom environment variables dictionary for a hosted bot."""
    bot = await get_bot(session, bot_id)
    if bot:
        bot.env_vars = env_vars
        bot.updated_at = datetime.now(timezone.utc)
        await session.flush()
    return bot


async def delete_bot(session: AsyncSession, bot_id: int) -> bool:
    """Delete a hosted bot and its associated logs from the database."""
    await session.execute(delete(BotLogEntry).where(BotLogEntry.bot_id == bot_id))
    stmt = delete(HostedBot).where(HostedBot.id == bot_id)
    result = await session.execute(stmt)
    await session.flush()
    return (result.rowcount or 0) > 0


async def add_bot_log(
    session: AsyncSession,
    bot_id: int,
    stream: str,
    message: str,
) -> BotLogEntry:
    """Persist a single log entry for a hosted bot."""
    entry = BotLogEntry(
        bot_id=bot_id,
        stream=stream,
        message=message,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_bot_logs_from_db(
    session: AsyncSession,
    bot_id: int,
    limit: int = 50,
) -> List[BotLogEntry]:
    """Retrieve persisted log entries for a bot ordered chronologically."""
    stmt = (
        select(BotLogEntry)
        .where(BotLogEntry.bot_id == bot_id)
        .order_by(BotLogEntry.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())
    # Return in ascending chronological order
    entries.reverse()
    return entries
