"""REST API, including API-only deployment and protected subscription settings."""
import hmac
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .config import Settings
from .models import Place
from .render import render_card
from .service import WeatherService
from .storage import Database

Style = Literal["minimal", "illustrated"]
Period = Literal["today", "week"]


class SubscriptionPatch(BaseModel):
    daily_time: str | None = None
    weekly_time: str | None = None
    weekly_day: int | None = Field(default=None, ge=0, le=6)
    clear: Literal["daily", "weekly", "all"] | None = None


def create_api(service: WeatherService, db: Database, settings: Settings) -> FastAPI:
    app = FastAPI(title="Wether Bot API", version="0.1.0")

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        if not settings.api_key:
            raise HTTPException(503, "Set API_KEY to enable administrative endpoints")
        if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(401, "Invalid API key")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "mode": settings.app_mode}

    @app.get("/v1/providers")
    async def providers() -> dict:
        return {"enabled": service.providers.available()}

    @app.get("/v1/geocode")
    async def geocode(q: str = Query(min_length=2, max_length=100)) -> dict:
        try:
            return {"results": [p.model_dump(mode="json") for p in await service.geocode(q)]}
        except Exception as exc:
            raise HTTPException(502, "Geocoding provider unavailable") from exc

    async def resolve(lat: float, lon: float, days: int, source: str | None):
        try:
            return await service.forecast(lat, lon, days, source)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/v1/forecast")
    async def forecast(
        lat: float = Query(ge=-90, le=90),
        lon: float = Query(ge=-180, le=180),
        days: int = Query(default=7, ge=1, le=16),
        source: str | None = None,
        output: Literal["both", "aggregate", "raw"] = "both",
    ) -> dict:
        result = await resolve(lat, lon, days, source)
        data = result.model_dump(mode="json")
        if output == "aggregate":
            data.pop("sources")
        elif output == "raw":
            for field in ("hours", "days"):
                data.pop(field)
        return data

    @app.get("/v1/card")
    async def card(
        lat: float = Query(ge=-90, le=90),
        lon: float = Query(ge=-180, le=180),
        city: str = Query(default="Мой город", min_length=1, max_length=100),
        style: Style = "illustrated",
        period: Period = "today",
    ) -> Response:
        result = await resolve(lat, lon, 7 if period == "week" else 2, None)
        return Response(render_card(city, result, style, period), media_type="image/png")

    @app.get("/v1/users/{chat_id}", dependencies=[Depends(require_key)])
    async def user(chat_id: int) -> dict:
        profile = await db.get(chat_id)
        if not profile:
            raise HTTPException(404, "Unknown user")
        return vars(profile)

    @app.put("/v1/users/{chat_id}/location", dependencies=[Depends(require_key)])
    async def put_location(chat_id: int, place: Place) -> dict:
        return vars(await db.set_location(chat_id, place))

    @app.patch("/v1/users/{chat_id}/subscription", dependencies=[Depends(require_key)])
    async def set_subscription(chat_id: int, update: SubscriptionPatch) -> dict:
        try:
            return vars(await db.update_subscription(chat_id, **update.model_dump()))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return app
