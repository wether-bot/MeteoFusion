"""Compact human-friendly Russian text formatting."""
from datetime import datetime, timezone

from .models import ForecastResult, ForecastHour


def condition(code: int | None) -> str:
    if code is None:
        return "Нет данных"
    if code == 0:
        return "Ясно"
    if code in (1, 2):
        return "Переменная облачность"
    if code == 3:
        return "Облачно"
    if code in (45, 48):
        return "Туман"
    if code in (51, 53, 55, 56, 57):
        return "Морось"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Дождь"
    if code in (71, 73, 75, 77, 85, 86):
        return "Снег"
    if code in (95, 96, 99):
        return "Гроза"
    return "Переменная погода"


def number(value: float | None, suffix: str = "", signed: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:+.0f}{suffix}" if signed else f"{value:.0f}{suffix}"


def relevant_hour(forecast: ForecastResult) -> ForecastHour | None:
    now = datetime.now(timezone.utc)
    return min(forecast.hours, key=lambda h: abs((h.time - now).total_seconds())) if forecast.hours else None


def forecast_text(city: str, forecast: ForecastResult, count: int = 3) -> str:
    hour = relevant_hour(forecast)
    result = [f"Погода · {city}"]
    if hour:
        result += [
            f"{condition(hour.weather_code)}, {number(hour.temperature_c, '°C', True)}",
            f"Ощущается: {number(hour.feels_like_c, '°C', True)}",
            f"Ветер: {number(hour.wind_kmh, ' км/ч')}; влажность: {number(hour.humidity_pct, '%')}",
            f"Осадки: {number(hour.precipitation_probability_pct, '%')} вероятность",
        ]
    if forecast.days:
        result.append("")
        result.append("Прогноз:")
        for day in forecast.days[:count]:
            result.append(
                f"{day['date']}: {number(day['temperature_min_c'], '°', True)}"
                f" … {number(day['temperature_max_c'], '°', True)}, "
                f"{condition(day['weather_code'])}"
            )
    result.append(f"Источников: {len(forecast.sources)}; независимых семейств: {forecast.contributor_count}")
    if forecast.errors:
        result.append("Недоступны: " + ", ".join(sorted(forecast.errors)))
    result.append("Данные модельные, прогноз не гарантирован.")
    return "\n".join(result)
