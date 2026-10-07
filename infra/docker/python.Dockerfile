# Used by the `app` profile in docker-compose and by the clean-machine check
# in Week 32.  Day-to-day development does NOT go through this image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY core ./core
COPY api ./api
COPY ml ./ml
RUN pip install --no-cache-dir -e .

EXPOSE 8001
# Shell form, not exec form, deliberately -- it is the only way CMD gets
# environment-variable substitution, so API_PORT (core/config.py's
# Settings.api_port) can override the default at `docker run -e` time.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${API_PORT:-8001}
