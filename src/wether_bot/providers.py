"""Provider adapters; all providers return canonical UTC-aware hourly data."""
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .models import ForecastHour, Place, SourceForecast

OPEN_METEO_URL = "https://api.open-meteo.com"
HOURLY = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,"
    "precipitation,precipitation_probability,wind_speed_10m,"
    "wind_direction_10m,weather_code"
)


def utc_time(value: str, tz_name: str = "UTC") -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(tz_name))
        except (KeyError, ValueError):
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def wmo_from_openweather(code: int) -> int:
    if 200 <= code < 300:
        return 95
    if 300 <= code < 600:
        return 63
    if 600 <= code < 700:
        return 73
    if 700 <= code < 800:
        return 45
    return {800: 0, 801: 1, 802: 2, 803: 3, 804: 3}.get(code, 0)


class WeatherProviders:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def available(self) -> list[str]:
        sources: list[str] = []
        if self.settings.enable_open_meteo:
            sources.append("open_meteo")
        if self.settings.enable_gfs:
            sources.append("gfs")
        if self.settings.enable_icon:
            sources.append("icon")
        if self.settings.enable_ecmwf:
            sources.append("ecmwf")
        if self.settings.enable_met_no:
            sources.append("met_no")
        if self.settings.openweather_api_key:
            sources.append("openweather")
        if self.settings.weatherapi_key:
            sources.append("weatherapi")
        return sources

    async def geocode(self, query: str) -> list[Place]:
        response = await self.client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 8, "language": "ru", "format": "json"},
        )
        response.raise_for_status()
        return [
            Place.model_validate({
                "name": item["name"],
                "country": item.get("country"),
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "timezone": item.get("timezone") or "UTC",
                "admin1": item.get("admin1"),
            })
            for item in response.json().get("results", [])
        ]

    async def fetch(self, name: str, lat: float, lon: float, days: int) -> SourceForecast:
        if name == "open_meteo":
            return await self.open_meteo(name, "/v1/forecast", "blend", lat, lon, days)
        if name == "gfs":
            return await self.open_meteo(name, "/v1/gfs", "gfs", lat, lon, min(days, 7))
        if name == "icon":
            return await self.open_meteo(name, "/v1/dwd-icon", "icon", lat, lon, min(days, 7))
        if name == "ecmwf":
            return await self.open_meteo(name, "/v1/ecmwf", "ecmwf", lat, lon, min(days, 10))
        if name == "met_no":
            return await self.met_no(lat, lon, days)
        if name == "openweather" and self.settings.openweather_api_key:
            return await self.openweather(lat, lon, days)
        if name == "weatherapi" and self.settings.weatherapi_key:
            return await self.weatherapi(lat, lon, days)
        raise ValueError(f"Provider not enabled: {name}")

    async def open_meteo(
        self, name: str, path: str, family: str, lat: float, lon: float, days: int
    ) -> SourceForecast:
        response = await self.client.get(
            OPEN_METEO_URL + path,
            params={
                "latitude": lat, "longitude": lon, "hourly": HOURLY,
                "timezone": "auto", "forecast_days": days,
            },
        )
        response.raise_for_status()
        raw = response.json()
        zone = raw.get("timezone") or "UTC"
        data = raw.get("hourly") or {}
        timestamps = data.get("time") or []

        def at(field: str, i: int) -> float | None:
            values = data.get(field) or []
            return safe_number(values[i]) if i < len(values) else None

        hours = [
            ForecastHour(
                time=utc_time(t, zone),
                temperature_c=at("temperature_2m", i),
                feels_like_c=at("apparent_temperature", i),
                humidity_pct=at("relative_humidity_2m", i),
                precipitation_mm=at("precipitation", i),
                precipitation_probability_pct=at("precipitation_probability", i),
                wind_kmh=at("wind_speed_10m", i),
                wind_direction_deg=at("wind_direction_10m", i),
                weather_code=int(at("weather_code", i))
                if at("weather_code", i) is not None else None,
            )
            for i, t in enumerate(timestamps)
        ]
        return SourceForecast(source=name, model_family=family, timezone=zone, hours=hours)

    async def met_no(self, lat: float, lon: float, days: int) -> SourceForecast:
        response = await self.client.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": round(lat, 4), "lon": round(lon, 4)},
            headers={"User-Agent": self.settings.met_user_agent},
        )
        response.raise_for_status()
        raw = response.json()
        hours = []
        for item in raw.get("properties", {}).get("timeseries", []):
            inst = item.get("data", {}).get("instant", {}).get("details", {})
            next_hour = item.get("data", {}).get("next_1_hours", {})
            details = next_hour.get("details") or {}
            code = next_hour.get("summary", {}).get("symbol_code")
            hours.append(ForecastHour(
                time=utc_time(item["time"]),
                temperature_c=safe_number(inst.get("air_temperature")),
                humidity_pct=safe_number(inst.get("relative_humidity")),
                wind_kmh=round(float(inst["wind_speed"]) * 3.6, 2)
                if inst.get("wind_speed") is not None else None,
                wind_direction_deg=safe_number(inst.get("wind_from_direction")),
                precipitation_mm=safe_number(details.get("precipitation_amount")),
                weather_code=met_symbol_to_wmo(code),
            ))
        return SourceForecast(source="met_no", model_family="ecmwf", hours=hours)

    async def weatherapi(self, lat: float, lon: float, days: int) -> SourceForecast:
        response = await self.client.get(
            "https://api.weatherapi.com/v1/forecast.json",
            params={
                "key": self.settings.weatherapi_key,
                "q": f"{lat},{lon}", "days": min(days, 14), "aqi": "no", "alerts": "no",
            },
        )
        response.raise_for_status()
        raw = response.json()
        zone = raw.get("location", {}).get("tz_id") or "UTC"
        hours = []
        for day in raw.get("forecast", {}).get("forecastday", []):
            for h in day.get("hour", []):
                hours.append(ForecastHour(
                    time=datetime.fromtimestamp(h["time_epoch"], tz=timezone.utc),
                    temperature_c=safe_number(h.get("temp_c")),
                    feels_like_c=safe_number(h.get("feelslike_c")),
                    humidity_pct=safe_number(h.get("humidity")),
                    precipitation_mm=safe_number(h.get("precip_mm")),
                    precipitation_probability_pct=max(
                        float(h.get("chance_of_rain") or 0), float(h.get("chance_of_snow") or 0)
                    ),
                    wind_kmh=safe_number(h.get("wind_kph")),
                    wind_direction_deg=safe_number(h.get("wind_degree")),
                    weather_code=None,
                ))
        return SourceForecast(source="weatherapi", model_family="weatherapi_blend", timezone=zone, hours=hours)

    async def openweather(self, lat: float, lon: float, days: int) -> SourceForecast:
        response = await self.client.get(
            "https://api.openweathermap.org/data/3.0/onecall",
            params={
                "lat": lat, "lon": lon, "appid": self.settings.openweather_api_key,
                "units": "metric", "exclude": "minutely,alerts",
            },
        )
        response.raise_for_status()
        raw = response.json()
        hours = []
        for item in raw.get("hourly", []):
            weather = item.get("weather") or []
            hours.append(ForecastHour(
                time=datetime.fromtimestamp(item["dt"], tz=timezone.utc),
                temperature_c=safe_number(item.get("temp")),
                feels_like_c=safe_number(item.get("feels_like")),
                humidity_pct=safe_number(item.get("humidity")),
                precipitation_mm=safe_number((item.get("rain") or {}).get("1h", 0)),
                precipitation_probability_pct=round(float(item.get("pop", 0)) * 100, 2),
                wind_kmh=round(float(item["wind_speed"]) * 3.6, 2)
                if item.get("wind_speed") is not None else None,
                wind_direction_deg=safe_number(item.get("wind_deg")),
                weather_code=wmo_from_openweather(weather[0]["id"]) if weather else None,
            ))
        return SourceForecast(
            source="openweather", model_family="openweather_blend",
            timezone=raw.get("timezone") or "UTC", hours=hours,
        )


def met_symbol_to_wmo(symbol: str | None) -> int | None:
    if not symbol:
        return None
    if "thunder" in symbol:
        return 95
    if "snow" in symbol:
        return 73
    if "sleet" in symbol:
        return 67
    if "rain" in symbol:
        return 63
    if "fog" in symbol:
        return 45
    if "cloudy" in symbol:
        return 3
    if "partlycloudy" in symbol:
        return 2
    if "fair" in symbol:
        return 1
    if "clearsky" in symbol:
        return 0
    return None
