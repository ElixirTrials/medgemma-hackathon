FROM python:3.12-slim AS base

# Install system dependencies for health check
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy workspace root files needed for uv resolution
COPY pyproject.toml uv.lock ./

# Copy all libs (needed for workspace resolution)
COPY libs/ libs/

# Copy this service
COPY services/api-service/ services/api-service/

# Copy alembic configuration
COPY services/api-service/alembic.ini services/api-service/alembic.ini
COPY services/api-service/alembic/ services/api-service/alembic/

# Install dependencies using uv
RUN uv sync --frozen --no-dev --package api-service

# Runtime
EXPOSE 8000
CMD ["sh", "-c", "cd services/api-service && uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn api_service.main:app --host 0.0.0.0 --port 8000"]
