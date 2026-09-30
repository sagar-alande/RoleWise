FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PROMPTS_DIR=/app/prompts

# Build context is the repo root (see docker-compose.yml and infra/README.md) so this stage can
# reach packages/prompts, which lives outside apps/backend. Local dev still overrides PROMPTS_DIR
# to a separate bind-mounted /prompts (see docker-compose.yml), so it never depends on this copy.
COPY apps/backend .
RUN pip install --no-cache-dir -e ".[dev]"
COPY packages/prompts ./prompts

EXPOSE 8000
# Default entrypoint is the API. The worker overrides the command with: python -m rolewise.worker.main
CMD ["uvicorn", "rolewise.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
