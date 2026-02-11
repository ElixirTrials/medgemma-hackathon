FROM python:3.12-slim AS base

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy workspace root files needed for uv resolution
COPY pyproject.toml uv.lock ./

# Copy all libs (needed for workspace resolution)
COPY libs/ libs/

# Copy this service
COPY services/agent-a-service/ services/agent-a-service/

# Install dependencies using uv
RUN uv sync --frozen --no-dev --package agent-a-service

# Runtime
EXPOSE 8001
CMD ["uv", "run", "--no-sync", "python", "-m", "agent_a_service"]
