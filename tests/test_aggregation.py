from datetime import datetime, timedelta, timezone

from wether_bot.aggregation import combine_forecasts
from wether_bot.models import ForecastHour, SourceForecast


def test_deduplicates_same_model_and_falls_back_to_blend():
    one = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    two = one + timedelta(hours=1)

    def source(name, family, readings):
        return SourceForecast(
            source=name, model_family=family,
            hours=[ForecastHour(time=t, temperature_c=v) for t, v in readings],
        )

    result = combine_forecasts([
        source("ecmwf", "ecmwf", [(one, 10)]),
        source("met_no", "ecmwf", [(one, 20)]),
        source("gfs", "gfs", [(one, 30)]),
        source("open_meteo", "blend", [(one, 90), (two, 42)]),
    ], 54.0, 56.0, 2)

    assert len(result.hours) == 2
    assert result.hours[0].temperature_c == 22.5
    assert result.hours[1].temperature_c == 42
    assert result.contributor_count == 2


def test_wind_direction_wraparound():
    stamp = datetime.now(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    ) + timedelta(hours=1)
    sources = [
        SourceForecast(source="a", model_family="gfs", hours=[
            ForecastHour(time=stamp, wind_direction_deg=350)
        ]),
        SourceForecast(source="b", model_family="icon", hours=[
            ForecastHour(time=stamp, wind_direction_deg=10)
        ]),
    ]
    result = combine_forecasts(sources, 0, 0, 1)
    assert abs(result.hours[0].wind_direction_deg - 0) < 0.1 or abs(
        result.hours[0].wind_direction_deg - 360
    ) < 0.1
