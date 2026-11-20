from datetime import datetime, timedelta, timezone
from io import BytesIO

from PIL import Image

from wether_bot.models import ForecastHour, ForecastResult
from wether_bot.render import render_card


def sample_forecast():
    stamp = datetime.now(timezone.utc) + timedelta(hours=1)
    return ForecastResult(
        latitude=54, longitude=56, timezone="UTC",
        hours=[ForecastHour(time=stamp, temperature_c=5, weather_code=2)],
        days=[{
            "date": "2026-11-22", "temperature_min_c": -2,
            "temperature_max_c": 6, "weather_code": 2,
        }],
        sources=[], contributor_count=2,
    )


def test_render_both_styles_and_periods():
    forecast = sample_forecast()
    for style in ("minimal", "illustrated"):
        for period in ("today", "week"):
            result = render_card("Ишимбай", forecast, style, period)
            with Image.open(BytesIO(result)) as image:
                assert image.format == "PNG"
                assert image.size == ((1200, 880) if period == "week" else (1000, 570))
