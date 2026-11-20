FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --home-dir /app --uid 10001 weather \
    && mkdir -p /data && chown weather:weather /data

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install ".[all]"

USER weather
VOLUME /data
EXPOSE 8000
CMD ["wether-bot"]
