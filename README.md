# Wether Bot

A Python weather aggregator with three deployment modes: **Telegram + REST API**,
**Telegram only**, or **REST API only**. SQLite is the default; PostgreSQL and Redis are optional.

## Features

- Multiple independent weather model families (NOAA GFS, DWD ICON, ECMWF) plus
  blended Open-Meteo, MET Norway, and optional OpenWeather/WeatherAPI integrations.
- Aggregation by model family; the API can return **raw per-source data**, aggregated
  hourly and daily values, or both. A blended forecast is used as fallback when
  no model-specific data is available for a timestamp.
- Location search, current and upcoming forecasts (up to 16 days where supported).
- Daily and weekly Telegram subscriptions at the location's local time.
- Local PNG image generation, in **minimal** and **illustrated** layouts, for
  **today** or a **weekly** forecast.
- Shared in-memory cache (optional Redis) and resilient partial provider failures.

## Quick start

```sh
cp .env.example .env
# Add BOT_TOKEN when APP_MODE=all or APP_MODE=telegram
docker compose up -d
```

To run only the API set `APP_MODE=api` (no Telegram bot token required).
The API defaults to http://localhost:8000; interactive docs are at `/docs`.

```sh
curl 'http://localhost:8000/v1/geocode?q=Москва'
curl 'http://localhost:8000/v1/forecast?lat=55.75&lon=37.62&days=7&output=both'
curl -o weather.png 'http://localhost:8000/v1/card?lat=55.75&lon=37.62&city=Москва&style=illustrated&period=week'
```

Set `API_KEY` to enable the protected user/subscription management endpoints;
send it via the `X-API-Key` header. Weather and geocoding are public reads.

Telegram: send the bot a city name or location, then use `/weather`,
`/card`, `/daily 07:00`, `/weekly 0 09:00`, `/off`, or `/help`.
Weekly weekday index: 0 Monday through 6 Sunday.

## Storage and deployment

`DATABASE_URL=sqlite+aiosqlite:////data/weather.db` by default; stored in
the persistent Docker `weather_data` volume. PostgreSQL: use
`postgresql+asyncpg://user:password@host:5432/weather` and the `postgres`
dependency extra. Redis: set `REDIS_URL` and install the `redis` extra.

Published Docker tags: `ghcr.io/wether-bot/wether-bot:latest` for a release,
`:edge` for main, and semantic version tags for release builds.

### Provider attribution and API policies

Open-Meteo and MET Norway are publicly accessible but require compliance with
their attribution, caching and usage conditions. For commercial usage, review
their licenses separately. Set a contactable `MET_USER_AGENT` and use the
optional vendor API keys only on plans that include the required endpoints.

This service is a forecast aggregator, not an official source for weather alerts.
It does not claim probabilistic confidence from simple model disagreement.

## Development

```sh
python -m pip install -e '.[all,dev]'
pytest
ruff check src tests
```

See `docs/ARCHITECTURE.md` for details and implementation limitations.
