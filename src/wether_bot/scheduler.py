"""Durable subscription definitions, scheduler tick and Telegram delivery."""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import BufferedInputFile

from .formatting import forecast_text
from .render import render_card
from .service import WeatherService
from .storage import Database, UserProfile

log = logging.getLogger(__name__)


def due_kinds(profile: UserProfile, now: datetime) -> list[tuple[str, str]]:
    if not profile.city:
        return []
    try:
        local = now.astimezone(ZoneInfo(profile.timezone))
    except (KeyError, ValueError):
        local = now.astimezone(timezone.utc)
    current_minute = local.hour * 60 + local.minute
    result = []

    def within_window(value: str | None) -> bool:
        if value is None:
            return False
        hour, minute = map(int, value.split(":"))
        target = hour * 60 + minute
        return 0 <= current_minute - target < 10

    day_key = local.date().isoformat()
    if within_window(profile.daily_time) and profile.last_daily_key != day_key:
        result.append(("daily", day_key))
    iso = local.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02}"
    if (profile.weekly_day == local.weekday() and within_window(profile.weekly_time)
            and profile.last_weekly_key != week_key):
        result.append(("weekly", week_key))
    return result


async def deliver(bot: Bot, db: Database, service: WeatherService, now: datetime) -> None:
    profiles = await db.subscriptions()
    for profile in profiles:
        for kind, key in due_kinds(profile, now):
            try:
                days = 7 if kind == "weekly" else 2
                forecast = await service.forecast(profile.latitude, profile.longitude, days)
                style = "illustrated"
                period = "week" if kind == "weekly" else "today"
                content = render_card(profile.city, forecast, style, period)
                caption = forecast_text(profile.city, forecast, count=7 if kind == "weekly" else 1)
                await bot.send_photo(
                    chat_id=profile.chat_id,
                    photo=BufferedInputFile(content, filename=f"{kind}.png"),
                    caption=caption[:1024],
                )
                await db.mark_sent(profile.chat_id, kind, key)
            except Exception:
                log.exception("Failed %s report for Telegram chat %d", kind, profile.chat_id)
