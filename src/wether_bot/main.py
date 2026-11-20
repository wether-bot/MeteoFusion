"""ASGI API and Telegram polling can run together or independently."""
import asyncio
import logging

import httpx
import uvicorn
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .api import create_api
from .bot import create_router
from .cache import Cache
from .config import get_settings
from .scheduler import deliver
from .service import WeatherService
from .storage import Database


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    if settings.app_mode in ("all", "telegram") and not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required when APP_MODE includes Telegram")

    db = Database(settings.database_url)
    await db.init()
    cache = Cache(settings)
    await cache.start()
    scheduler = None

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/json"},
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        ) as client:
            service = WeatherService(settings, client, cache)
            if settings.app_mode == "api":
                app = create_api(service, db, settings)
                server = uvicorn.Server(uvicorn.Config(
                    app, host=settings.api_host, port=settings.api_port, log_level="info"
                ))
                await server.serve()
                return

            async with Bot(token=settings.bot_token) as bot:
                dp = Dispatcher()
                dp.include_router(create_router(service, db))
                scheduler = AsyncIOScheduler(timezone="UTC")
                scheduler.add_job(
                    deliver, "interval", seconds=60, args=(bot, db, service),
                    kwargs={}, max_instances=1, coalesce=True,
                )
                # Scheduler argument 'now' is evaluated on every tick, not at registration.
                scheduler.remove_all_jobs()
                async def tick() -> None:
                    from datetime import datetime, timezone
                    await deliver(bot, db, service, datetime.now(timezone.utc))
                scheduler.add_job(tick, "interval", seconds=60, max_instances=1, coalesce=True)
                scheduler.start()

                if settings.app_mode == "telegram":
                    await dp.start_polling(bot)
                else:
                    app = create_api(service, db, settings)
                    server = uvicorn.Server(uvicorn.Config(
                        app, host=settings.api_host, port=settings.api_port, log_level="info"
                    ))
                    tasks = [
                        asyncio.create_task(server.serve(), name="api"),
                        asyncio.create_task(
                            dp.start_polling(bot, handle_signals=False), name="telegram"
                        ),
                    ]
                    try:
                        done, pending = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        await cache.close()
        await db.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
