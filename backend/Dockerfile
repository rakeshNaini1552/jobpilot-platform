# JobPilot backend — one image serves api / worker / beat (command differs).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/jobpilot

# Install dependencies first for layer caching.
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install .

# Non-root runtime user.
RUN useradd --create-home jobpilot && chown -R jobpilot /srv/jobpilot
USER jobpilot

EXPOSE 8000

# Default command = API. Compose overrides for worker/beat.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
