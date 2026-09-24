FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PROMPTS_DIR=/app/prompts

COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

# CI copies packages/prompts into apps/backend/prompts before building.
# Locally, docker compose mounts the prompts folder instead.
RUN mkdir -p /app/prompts

EXPOSE 8000
# Default entrypoint is the API. The worker overrides the command with: python -m rolewise.worker.main
CMD ["uvicorn", "rolewise.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
