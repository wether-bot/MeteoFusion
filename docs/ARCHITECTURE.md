# Architecture

## Runtime modes

- `all`: run FastAPI and aiogram polling in one process. Scheduler sends
  daily and weekly reports over Telegram.
- `telegram`: polling + scheduled delivery, without an HTTP listener.
- `api`: FastAPI only; no Telegram token needed and no Telegram scheduler.

A single polling/scheduler instance is required for a single Telegram bot
token. Multiple API-only replicas may share PostgreSQL/Redis.

## Forecast pipeline

1. Shared async HTTP client requests configured provider adapters concurrently.
2. Provider-specific fields are normalized to UTC-aware hourly records in
   temperature °C, wind km/h, precipitation mm, humidity %, WMO codes.
3. Cached normalized forecasts are reused across users at nearby coordinates.
4. Sources are grouped by their underlying model family. MET Norway and
   ECMWF are considered related; blending does not naively count twice.
5. Each numeric field is combined per family and then across families;
   wind direction uses circular averaging and categorical weather codes
   use majority voting.
6. Local daily summaries are reconstructed from the combined hours.

This is an arithmetic aggregation baseline, not a trained statistical
forecast. Probabilities are not yet recalibrated using historical observations.
No historical truth labels or model accuracy weights are collected yet.
More sophisticated location/horizon-dependent weights are a later milestone.

A selected model may cover fewer days than the blended Open-Meteo forecast:
an hourly fallback to the blended data is intended when no model-specific
samples exist for that instant.

## Providers

- Open-Meteo blended forecast, NOAA GFS, DWD ICON, ECMWF IFS (no API keys).
- MET Norway Locationforecast (requires identifying User-Agent, ECMWF family).
- OpenWeather One Call 3.0 (requires suitable plan and key).
- WeatherAPI forecast.json (requires key; available horizon depends on plan).

Any provider failure is isolated and the response includes an error map.
If all providers fail, the API returns HTTP 502.

Provider terms, attribution and forecast coverage should be reviewed before
public or commercial deployments.

## Storage and scheduled jobs

SQLite is default, PostgreSQL is available via SQLAlchemy. Database tables
are created at startup; use Alembic migrations before changing deployed schema.
Subscription delivery keys are persisted to avoid duplicate dispatch on
normal 60-second scheduler ticks. This is not distributed at-most-once delivery:
run exactly one scheduler, or implement atomic delivery leases before scaling
the worker horizontally.

Ten-minute send windows tolerate small timer drift but not long downtime.
Telegram blocking/deletion errors are logged rather than dropping a user's
settings automatically.

Redis is an optional best-effort cross-instance cache. Without Redis,
the in-process cache has per-key async locks and a TTL.

## API security

GET forecast, provider metadata, geocoding, and PNG cards are intentionally
public. Set API_KEY to enable state-changing endpoints; without API_KEY, they
return 503. Keep API_KEY secret, use TLS and put rate limiting at the reverse
proxy for public deployments. Chat IDs are not authentication credentials.

## Image generation

Pillow performs deterministic offline rendering of a minimal and an
illustrated gradient PNG, for one-day or weekly layouts. This is not an
AI art generation service and does not download external images.

## Limitations and next milestones

- City disambiguation UI, multiple cities per user, local time preferences.
- Historical verification and trained model-specific aggregation weights.
- Alerts, quiet hours, per-user image and notification layout preferences.
- Better WMO mapping for third-party provider condition codes.
- Explicit provider license attribution in each delivered output.
- API pagination/rate-limiting, structured metrics, health checks of providers.
- Proper database migration management and atomic distributed deliveries.
