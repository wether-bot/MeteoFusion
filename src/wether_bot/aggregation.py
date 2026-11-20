"""Combine by independent model family, not blindly by API vendor."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, median
from zoneinfo import ZoneInfo

from .models import ForecastHour, ForecastResult, SourceForecast


def combine_forecasts(
    forecasts: list[SourceForecast],
    latitude: float,
    longitude: float,
    days: int,
    errors: dict[str, str] | None = None,
) -> ForecastResult:
    if not forecasts:
        raise ValueError("Cannot aggregate zero forecasts")
    tz_name = next((f.timezone for f in forecasts if f.timezone != "UTC"), "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, ValueError):
        tz = timezone.utc
        tz_name = "UTC"
    # A blended multi-model API forecast is not an independent extra weather model.
    candidates = (
        [f for f in forecasts if f.model_family != "blend"]
        if any(f.model_family != "blend" for f in forecasts)
        else forecasts
    )
    groups: dict[datetime, dict[str, list[ForecastHour]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for forecast in candidates:
        for hour in forecast.hours:
            stamp = hour.time.astimezone(timezone.utc)
            groups[stamp][forecast.model_family].append(hour)

    fields = (
        "temperature_c", "feels_like_c", "humidity_pct", "precipitation_mm",
        "precipitation_probability_pct", "wind_kmh",
    )

    def average(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        return round(mean(valid), 2) if valid else None

    result_hours = []
    for stamp in sorted(groups):
        by_family = groups[stamp]
        values = {}
        for field in fields:
            per_model = [average([getattr(h, field) for h in hours])
                         for hours in by_family.values()]
            values[field] = average(per_model)
        # Circular mean for wind direction (0° == 360°).
        import math
        vectors = []
        for hours in by_family.values():
            angles = [math.radians(h.wind_direction_deg) for h in hours
                      if h.wind_direction_deg is not None]
            if angles:
                a = math.atan2(mean([math.sin(x) for x in angles]),
                               mean([math.cos(x) for x in angles]))
                vectors.append(a)
        if vectors:
            direction = math.degrees(math.atan2(
                mean([math.sin(a) for a in vectors]),
                mean([math.cos(a) for a in vectors]),
            )) % 360
            values["wind_direction_deg"] = round(direction, 1)
        codes = [h.weather_code for members in by_family.values()
                 for h in members if h.weather_code is not None]
        values["weather_code"] = Counter(codes).most_common(1)[0][0] if codes else None
        result_hours.append(ForecastHour(time=stamp, **values))

    now = datetime.now(timezone.utc)
    result_hours = [h for h in result_hours if h.time >= now.replace(minute=0, second=0, microsecond=0)]
    # Daily calendar grouping uses local weather-location timezone.
    daily: dict[str, list[ForecastHour]] = defaultdict(list)
    for hour in result_hours:
        daily[hour.time.astimezone(tz).date().isoformat()].append(hour)
    days_result = []
    for date, hours in sorted(daily.items())[:days]:
        temperatures = [h.temperature_c for h in hours if h.temperature_c is not None]
        chances = [h.precipitation_probability_pct for h in hours
                   if h.precipitation_probability_pct is not None]
        winds = [h.wind_kmh for h in hours if h.wind_kmh is not None]
        codes = [h.weather_code for h in hours if h.weather_code is not None]
        precip = [h.precipitation_mm for h in hours if h.precipitation_mm is not None]
        days_result.append({
            "date": date,
            "temperature_min_c": min(temperatures) if temperatures else None,
            "temperature_max_c": max(temperatures) if temperatures else None,
            "precipitation_sum_mm": round(sum(precip), 2) if precip else None,
            "precipitation_probability_max_pct": max(chances) if chances else None,
            "wind_max_kmh": max(winds) if winds else None,
            "weather_code": Counter(codes).most_common(1)[0][0] if codes else None,
            "hour_count": len(hours),
        })
    return ForecastResult(
        latitude=latitude, longitude=longitude, timezone=tz_name,
        hours=result_hours, days=days_result, sources=forecasts, errors=errors or {},
        contributor_count=len({f.model_family for f in candidates}),
    )


def temperature_spread(forecasts: list[SourceForecast], when: datetime) -> float | None:
    """Unweighted diagnostic range, not a calibrated probability."""
    readings = [h.temperature_c for f in forecasts for h in f.hours
                if h.time == when and h.temperature_c is not None]
    return round(max(readings) - min(readings), 2) if len(readings) > 1 else None
