"""Weather application service with independent provider failure handling."""
import asyncio
import logging

import httpx

from .aggregation import combine_forecasts
from .cache import Cache
from .config import Settings
from .models import ForecastResult, Place, SourceForecast
from .providers import WeatherProviders

log = logging.getLogger(__name__)


class WeatherService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient, cache: Cache):
        self.settings = settings
        self.providers = WeatherProviders(client, settings)
        self.cache = cache

    async def geocode(self, query: str) -> list[Place]:
        query = query.strip()
        if len(query) < 2 or len(query) > 100:
            raise ValueError("City name must be 2-100 characters")
        async def work() -> dict:
            places = await self.providers.geocode(query)
            return {"results": [p.model_dump(mode="json") for p in places]}
        data = await self.cache.get_or_set(f"geocode:v1:{query.casefold()}", work)
        return [Place.model_validate(p) for p in data["results"]]

    async def forecast(
        self, lat: float, lon: float, days: int = 7, source: str | None = None,
    ) -> ForecastResult:
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid coordinates")
        if not 1 <= days <= 16:
            raise ValueError("Days must be 1-16")
        names = self.providers.available()
        if source and source not in names:
            raise ValueError("Unknown or disabled provider")
        selected = [source] if source else names

        async def load(name: str) -> SourceForecast:
            key = f"forecast:v2:{name}:{round(lat, 3)}:{round(lon, 3)}:{days}"
            async def work() -> dict:
                result = await self.providers.fetch(name, lat, lon, days)
                return result.model_dump(mode="json")
            return SourceForecast.model_validate(await self.cache.get_or_set(key, work))

        items = await asyncio.gather(*(load(name) for name in selected), return_exceptions=True)
        successful = []
        errors = {}
        for name, item in zip(selected, items, strict=True):
            if isinstance(item, BaseException):
                log.warning("Weather source %s failed: %s", name, item)
                errors[name] = type(item).__name__
            else:
                successful.append(item)
        if not successful:
            raise RuntimeError("All weather sources are unavailable")
        return combine_forecasts(successful, lat, lon, days, errors)
