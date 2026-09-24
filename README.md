# RoleWise

An AI career assistant that finds suitable jobs, explains every match, and identifies resume gaps, using
only information the candidate has verified.

## Repository layout

```
CLAUDE.md                 rules for Claude Code (Cursor mirror in .cursor/rules)
docs/                     architecture and decision records
apps/web/                 Next.js frontend
apps/backend/             FastAPI API + SQS worker (one image, two entrypoints)
packages/prompts/         versioned LLM prompts
evals/                    golden datasets and evaluation scripts
infra/                    AWS CDK stack (ECS Express Mode, RDS, S3, SQS, Cognito)
.github/workflows/        CI and deploy pipelines
docker-compose.yml        full local stack
```

## Quick start (local)

Requirements: Docker Desktop, Node 20+, Python 3.11+.

```
cp .env.example .env
make up          # starts postgres, localstack, api, worker, web
make migrate     # creates tables
```

- Web: http://localhost:3000
- API docs: http://localhost:8000/docs

Local mode uses `BEDROCK_ENABLED=false`, so AI calls return deterministic stubs and no AWS account is needed.
Set `BEDROCK_ENABLED=true` with AWS credentials to use real Bedrock models.

Local auth: when `APP_ENV=local`, send the header `X-Dev-User: you@example.com` instead of a Cognito token.
The web app does this automatically in local mode.

## MVP scope

Profile and verified facts, resume parsing, job ingestion (Greenhouse public boards and pasted jobs),
explainable match scoring, gap analysis, and the recommendation dashboard.

## Deployment

See `docs/architecture.md` and `infra/README.md`. Services run on Amazon ECS Express Mode.
