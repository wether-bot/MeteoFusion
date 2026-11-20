import pytest

from wether_bot.models import Place
from wether_bot.storage import Database
from wether_bot.scheduler import due_kinds
from datetime import datetime
from zoneinfo import ZoneInfo


@pytest.mark.asyncio
async def test_sqlite_subscriptions(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    try:
        await db.init()
        place = Place(name="Ишимбай", latitude=53.46, longitude=56.04, timezone="Asia/Yekaterinburg")
        await db.set_location(123, place)
        profile = await db.update_subscription(123, daily_time="07:00", weekly_time="09:00", weekly_day=0)
        assert profile.daily_time == "07:00"
        assert len(await db.subscriptions()) == 1
        now = datetime(2026, 11, 23, 7, 0, tzinfo=ZoneInfo("Asia/Yekaterinburg"))
        assert due_kinds(profile, now)[0][0] == "daily"
        assert await db.mark_sent(123, "daily", "2026-11-23")
        assert not await db.mark_sent(123, "daily", "2026-11-23")
        await db.update_subscription(123, clear="all")
        assert not await db.subscriptions()
    finally:
        await db.close()
