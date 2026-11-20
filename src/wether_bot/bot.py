"""Telegram interface; can be entirely disabled in API-only mode."""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from .formatting import forecast_text
from .models import Place
from .render import render_card
from .service import WeatherService
from .storage import Database

log = logging.getLogger(__name__)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сейчас", callback_data="wx:today"),
            InlineKeyboardButton(text="На неделю", callback_data="wx:week"),
        ],
        [
            InlineKeyboardButton(text="Карточка", callback_data="wx:card"),
            InlineKeyboardButton(text="Источники", callback_data="wx:sources"),
        ],
    ])


def create_router(service: WeatherService, db: Database) -> Router:
    router = Router(name="weather")

    async def display(message: Message, days: int = 3) -> None:
        profile = await db.get(message.chat.id)
        if not profile or not profile.city:
            await message.answer("Сначала отправь название города или геолокацию.")
            return
        try:
            forecast = await service.forecast(profile.latitude, profile.longitude, days)
        except Exception:
            log.exception("Could not fetch weather")
            await message.answer("Погодные источники временно недоступны.")
            return
        await message.answer(
            forecast_text(profile.city, forecast, count=days),
            reply_markup=main_keyboard(),
        )

    async def send_card(message: Message, style: str = "illustrated", period: str = "today") -> None:
        profile = await db.get(message.chat.id)
        if not profile or not profile.city:
            await message.answer("Сначала выбери город.")
            return
        try:
            forecast = await service.forecast(
                profile.latitude, profile.longitude, 7 if period == "week" else 2
            )
            photo = render_card(profile.city, forecast, style=style, period=period)
            await message.answer_photo(BufferedInputFile(photo, filename="weather.png"))
        except Exception:
            log.exception("Could not render weather card")
            await message.answer("Не удалось создать карточку погоды.")

    @router.message(Command("start", "help"))
    async def start(message: Message) -> None:
        await message.answer(
            "Привет! Отправь название города или геолокацию.\n\n"
            "/weather — погода\n/week — прогноз на неделю\n"
            "/card — картинка (по умолчанию иллюстрированная)\n"
            "/card minimal week — минималистичная недельная карточка\n"
            "/sources — источники\n"
            "/daily 07:00 — утренняя сводка\n"
            "/weekly 0 09:00 — сводка каждый понедельник\n"
            "/off — отключить рассылки\n"
            "/status — мои настройки"
        )

    @router.message(Command("weather"))
    async def weather(message: Message) -> None:
        await display(message)

    @router.message(Command("week"))
    async def week(message: Message) -> None:
        await display(message, 7)

    @router.message(Command("card"))
    async def card(message: Message) -> None:
        args = (message.text or "").split()[1:]
        style = "minimal" if "minimal" in args else "illustrated"
        period = "week" if "week" in args else "today"
        await send_card(message, style, period)

    @router.message(Command("sources"))
    async def sources(message: Message) -> None:
        await message.answer(
            "Активные источники: " + ", ".join(service.providers.available()) +
            "\nИсходные данные отдельно доступны через REST API /v1/forecast?output=raw."
        )

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        profile = await db.get(message.chat.id)
        if not profile or not profile.city:
            await message.answer("Город ещё не выбран.")
            return
        await message.answer(
            f"Город: {profile.city}\nЧасовой пояс: {profile.timezone}\n"
            f"Ежедневно: {profile.daily_time or 'отключено'}\n"
            f"Еженедельно: {str(profile.weekly_day) + ' ' + profile.weekly_time if profile.weekly_time is not None else 'отключено'}"
        )

    @router.message(Command("daily"))
    async def daily(message: Message) -> None:
        args = (message.text or "").split()
        if len(args) != 2:
            await message.answer("Использование: /daily 07:00")
            return
        try:
            profile = await db.update_subscription(message.chat.id, daily_time=args[1])
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await message.answer(f"Ежедневная сводка: {profile.daily_time} ({profile.timezone}).")

    @router.message(Command("weekly"))
    async def weekly(message: Message) -> None:
        args = (message.text or "").split()
        if len(args) != 3:
            await message.answer("Использование: /weekly 0 09:00 (0=пн, 6=вс)")
            return
        try:
            day = int(args[1])
            profile = await db.update_subscription(
                message.chat.id, weekly_day=day, weekly_time=args[2]
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await message.answer(f"Еженедельная сводка: день {day}, {profile.weekly_time}.")

    @router.message(Command("off"))
    async def off(message: Message) -> None:
        args = (message.text or "").split()
        kind = args[1] if len(args) > 1 else "all"
        if kind not in ("all", "daily", "weekly"):
            await message.answer("Использование: /off [daily|weekly|all]")
            return
        try:
            await db.update_subscription(message.chat.id, clear=kind)
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await message.answer("Рассылки отключены: " + kind)

    @router.message(F.location)
    async def location(message: Message) -> None:
        if message.location is None:
            return
        lat, lon = message.location.latitude, message.location.longitude
        try:
            forecast = await service.forecast(lat, lon, 1)
            zone = forecast.timezone
        except Exception:
            zone = "UTC"
        await db.set_location(message.chat.id, Place(
            name="Моя геолокация", latitude=lat, longitude=lon, timezone=zone
        ))
        await message.answer("Геолокация сохранена.")
        await display(message)

    @router.callback_query(F.data.startswith("wx:"))
    async def buttons(callback: CallbackQuery) -> None:
        await callback.answer()
        if not callback.message or not isinstance(callback.message, Message):
            return
        action = (callback.data or "").removeprefix("wx:")
        if action == "today":
            await display(callback.message, 3)
        elif action == "week":
            await display(callback.message, 7)
        elif action == "card":
            await send_card(callback.message)
        elif action == "sources":
            await sources(callback.message)

    @router.message(F.text)
    async def find_city(message: Message) -> None:
        query = (message.text or "").strip()
        if query.startswith("/"):
            await message.answer("Неизвестная команда. Используй /help.")
            return
        if len(query) < 2 or len(query) > 100:
            await message.answer("Название города должно содержать от 2 до 100 символов.")
            return
        try:
            matches = await service.geocode(query)
        except Exception:
            log.exception("City lookup error")
            await message.answer("Не удалось найти город: сервис поиска недоступен.")
            return
        if not matches:
            await message.answer("Город не найден. Уточни название или отправь геолокацию.")
            return
        place = matches[0]
        await db.set_location(message.chat.id, place)
        await message.answer(f"Выбран: {place.name}, {place.country or ''}.")
        await display(message)

    return router
