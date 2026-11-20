"""Offline PNG weather cards: minimal and illustrated; today and week."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .formatting import condition, number, relevant_hour
from .models import ForecastResult

FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    options = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ] + FONTS if bold else FONTS
    for path in options:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_cloud(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float, rainy: bool) -> None:
    s = scale
    draw.ellipse((x + 10*s, y + 13*s, x + 80*s, y + 75*s), fill="#FFF7EB")
    draw.ellipse((x + 56*s, y, x + 144*s, y + 82*s), fill="#FFF7EB")
    draw.ellipse((x + 113*s, y + 26*s, x + 170*s, y + 79*s), fill="#FFF7EB")
    draw.rounded_rectangle((x + 20*s, y + 44*s, x + 160*s, y + 85*s), radius=20*s, fill="#FFF7EB")
    if rainy:
        for j in range(3):
            xx = x + (45 + j * 42) * s
            draw.line((xx, y + 100*s, xx - 10*s, y + 127*s),
                      fill="#8DD7F4", width=max(2, int(6*s)))


def render_card(
    city: str, forecast: ForecastResult,
    style: str = "illustrated", period: str = "today",
) -> bytes:
    if style not in ("minimal", "illustrated"):
        raise ValueError("style must be minimal or illustrated")
    if period not in ("today", "week"):
        raise ValueError("period must be today or week")
    weekly = period == "week"
    width, height = (1200, 880) if weekly else (1000, 570)
    background = (248, 249, 252) if style == "minimal" else (21, 40, 73)
    foreground = "#17233A" if style == "minimal" else "#F8FCFF"
    muted = "#63738C" if style == "minimal" else "#C8D8EA"
    im = Image.new("RGB", (width, height), background)
    d = ImageDraw.Draw(im)

    if style == "illustrated":
        # Vertical sky gradient; composited cheaply without image-generation services.
        top = (19, 44, 86)
        bottom = (59, 112, 157)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            col = tuple(round(top[i] * (1-ratio) + bottom[i] * ratio) for i in range(3))
            d.line((0, y, width, y), fill=col)
        d.ellipse((width - 315, -135, width + 85, 265), fill="#F6BE75")
        draw_cloud(d, width - 310, 115, 1.3, False)
    else:
        d.rounded_rectangle((24, 24, width-24, height-24), radius=30,
                            outline="#DCE3ED", width=2)

    city = (city or "Город").strip()[:46]
    d.text((64, 55), city, font=font(46, True), fill=foreground)
    d.text((66, 118), "Сводка погоды" if not weekly else "Прогноз на неделю",
           font=font(25), fill=muted)

    hour = relevant_hour(forecast)
    if hour:
        d.text((64, 190), number(hour.temperature_c, "°C", True),
               font=font(104, True), fill=foreground)
        d.text((68, 320), condition(hour.weather_code), font=font(31), fill=foreground)
        d.text((68, 374), f"Ощущается: {number(hour.feels_like_c, '°C', True)}",
               font=font(23), fill=muted)
        d.text((68, 418), f"Ветер {number(hour.wind_kmh, ' км/ч')}   •   "
               f"Влажность {number(hour.humidity_pct, '%')}", font=font(23), fill=muted)
        d.text((68, 459),
               f"Вероятность осадков: {number(hour.precipitation_probability_pct, '%')}",
               font=font(23), fill=muted)
    else:
        d.text((64, 220), "Нет почасовых данных", font=font(32), fill=foreground)

    if weekly:
        y0 = 553
        d.line((65, y0-12, width-65, y0-12), fill=muted, width=2)
        for i, day in enumerate(forecast.days[:7]):
            col = i % 4
            row = i // 4
            x = 65 + col * 280
            y = y0 + row * 139
            d.text((x, y), day["date"][5:], font=font(24, True), fill=foreground)
            temps = f"{number(day['temperature_min_c'], '°', True)} / " \
                    f"{number(day['temperature_max_c'], '°', True)}"
            d.text((x, y + 37), temps, font=font(23), fill=foreground)
            d.text((x, y + 76), condition(day["weather_code"])[:18],
                   font=font(18), fill=muted)

    d.text((66, height-53),
           f"Wether Bot  •  {len(forecast.sources)} источников  •  "
           f"{forecast.contributor_count} семейств моделей",
           font=font(17), fill=muted)

    output = BytesIO()
    im.save(output, format="PNG", optimize=True)
    return output.getvalue()
