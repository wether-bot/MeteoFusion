"""Canonical provider-independent weather data models."""
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ForecastHour(BaseModel):
    time: datetime
    temperature_c: float | None = None
    feels_like_c: float | None = None
    humidity_pct: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability_pct: float | None = None
    wind_kmh: float | None = None
    wind_direction_deg: float | None = None
    weather_code: int | None = None


class SourceForecast(BaseModel):
    source: str
    model_family: str
    timezone: str = "UTC"
    hours: list[ForecastHour] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ForecastResult(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hours: list[ForecastHour]
    days: list[dict]
    sources: list[SourceForecast]
    errors: dict[str, str] = Field(default_factory=dict)
    contributor_count: int = 0
    note: str = "Model families are deduplicated; this is not an official weather warning."


class Place(BaseModel):
    name: str
    country: str | None = None
    latitude: float
    longitude: float
    timezone: str = "UTC"
    admin1: str | None = None
