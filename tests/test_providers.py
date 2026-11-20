import httpx
import pytest

from wether_bot.config import Settings
from wether_bot.providers import WeatherProviders


@pytest.mark.asyncio
async def test_open_meteo_normalization():
    def handler(request):
        assert request.url.path == "/v1/forecast"
        return httpx.Response(200, json={
            "timezone": "Europe/Moscow",
            "hourly": {
                "time": ["2026-11-22T10:00"],
                "temperature_2m": [5.5],
                "wind_speed_10m": [20],
                "precipitation_probability": [60],
                "weather_code": [61],
            },
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await WeatherProviders(client, Settings()).fetch(
            "open_meteo", 55, 37, 1
        )
    assert result.hours[0].temperature_c == 5.5
    assert result.hours[0].weather_code == 61
    assert result.hours[0].time.hour == 7  # Moscow UTC+3
