"""Async SQLAlchemy persistence. SQLite is the default; PostgreSQL is optional."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import BigInteger, Float, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .models import Place


class Base(DeclarativeBase):
    pass


class UserSettings(Base):
    __tablename__ = "user_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city: Mapped[str] = mapped_column(String(150), default="")
    latitude: Mapped[float] = mapped_column(Float, default=0)
    longitude: Mapped[float] = mapped_column(Float, default=0)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    daily_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    weekly_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    weekly_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_daily_key: Mapped[str | None] = mapped_column(String(12), nullable=True)
    last_weekly_key: Mapped[str | None] = mapped_column(String(12), nullable=True)


@dataclass(frozen=True)
class UserProfile:
    chat_id: int
    city: str
    latitude: float
    longitude: float
    timezone: str
    daily_time: str | None
    weekly_time: str | None
    weekly_day: int | None
    last_daily_key: str | None
    last_weekly_key: str | None

    @classmethod
    def from_row(cls, row: UserSettings) -> "UserProfile":
        return cls(**{name: getattr(row, name) for name in cls.__dataclass_fields__})


class Database:
    def __init__(self, url: str):
        if url.startswith("sqlite+aiosqlite:////"):
            path = Path(url.removeprefix("sqlite+aiosqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def get(self, chat_id: int) -> UserProfile | None:
        async with self.sessions() as session:
            row = await session.get(UserSettings, chat_id)
            return UserProfile.from_row(row) if row else None

    async def set_location(self, chat_id: int, place: Place) -> UserProfile:
        async with self.sessions.begin() as session:
            row = await session.get(UserSettings, chat_id)
            if row is None:
                row = UserSettings(chat_id=chat_id)
                session.add(row)
            row.city = place.name
            row.latitude = place.latitude
            row.longitude = place.longitude
            row.timezone = place.timezone
        profile = await self.get(chat_id)
        assert profile is not None
        return profile

    async def update_subscription(
        self,
        chat_id: int,
        *,
        daily_time: str | None = None,
        weekly_time: str | None = None,
        weekly_day: int | None = None,
        clear: str | None = None,
    ) -> UserProfile:
        async with self.sessions.begin() as session:
            row = await session.get(UserSettings, chat_id)
            if not row or not row.city:
                raise ValueError("Choose a city first")
            if clear in ("daily", "all"):
                row.daily_time = None
            if clear in ("weekly", "all"):
                row.weekly_time = None
                row.weekly_day = None
            if daily_time is not None:
                validate_time(daily_time)
                row.daily_time = daily_time
            if weekly_time is not None:
                validate_time(weekly_time)
                if weekly_day is None or not 0 <= weekly_day <= 6:
                    raise ValueError("Weekday must be in 0..6")
                row.weekly_time = weekly_time
                row.weekly_day = weekly_day
        profile = await self.get(chat_id)
        assert profile is not None
        return profile

    async def subscriptions(self) -> list[UserProfile]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(UserSettings).where(
                    (UserSettings.daily_time.is_not(None))
                    | (UserSettings.weekly_time.is_not(None))
                )
            )
            return [UserProfile.from_row(row) for row in result]

    async def mark_sent(self, chat_id: int, kind: str, key: str) -> bool:
        if kind not in ("daily", "weekly"):
            raise ValueError("Unknown subscription kind")
        async with self.sessions.begin() as session:
            row = await session.get(UserSettings, chat_id)
            if not row:
                return False
            attr = "last_daily_key" if kind == "daily" else "last_weekly_key"
            if getattr(row, attr) == key:
                return False
            setattr(row, attr, key)
            return True


def validate_time(value: str) -> None:
    try:
        hours, minutes = map(int, value.split(":"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Time must be HH:MM") from exc
    if not 0 <= hours <= 23 or not 0 <= minutes <= 59 or len(value) != 5:
        raise ValueError("Time must be HH:MM")
