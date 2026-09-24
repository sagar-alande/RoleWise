# RoleWise: rules for AI coding agents

RoleWise is an AI career assistant. It finds suitable jobs, explains every match, identifies resume gaps,
and (in V2) prepares truthful application materials. Read `docs/architecture.md` before large changes.

## Product invariants (never break these)

1. **Verified facts only.** Generated content (explanations, resumes, cover letters) may only make claims
   backed by `career_facts` rows where `verified = true`. Every generated claim stores `supporting_fact_ids`.
2. **No external action without approval.** `submit_application` runs only when an `approvals` row exists
   whose `payload_hash` matches the exact package. Never add a code path that skips this check.
3. **Never guess personal answers.** Salary, work authorization, demographics, relocation and start date
   go to the user through `request_user_input`.
4. **Allow-listed job sources only.** Connectors must be registered in `job_sources` with `terms_ok = true`.
   Do not add scrapers for LinkedIn, Indeed or any site whose terms forbid automated access.
5. **No personal data in logs or LLM traces.** Log ids, never resume text, emails or names.
6. **The match score is deterministic.** `rolewise/services/matching.py` computes it. The LLM only explains
   the breakdown. It never produces or changes the number.

## Stack

- `apps/web`: Next.js 15 (App Router), React, TypeScript, Tailwind CSS
- `apps/backend`: Python 3.11, FastAPI, SQLAlchemy 2, Alembic, pgvector. One image, two entrypoints:
  `rolewise.api.main:app` (API) and `rolewise.worker.main` (SQS worker)
- `infra`: AWS CDK (TypeScript). Deploys to Amazon ECS Express Mode (App Runner is closed to new customers)
- AI: Amazon Bedrock (Claude models + Titan Text Embeddings V2, 1024 dims). `BEDROCK_ENABLED=false` uses
  deterministic local stubs so tests and local dev need no AWS access.

## Commands

```
make up          # Postgres+pgvector, LocalStack (S3, SQS), api, worker, web
make migrate     # alembic upgrade head
make test        # backend pytest
make lint        # ruff + web typecheck
make evals       # run evals/ against the golden datasets
```

## Conventions

- Pydantic schemas in `rolewise/schemas.py` for every request and response. No untyped dicts at API edges.
- Database access only through SQLAlchemy models. Every schema change ships an Alembic migration.
- Prompts live in `packages/prompts/*.vN.md`. Change a prompt by adding a new version, and store
  `prompt_version` with the output.
- Slow AI work (parsing, ingestion, embeddings, scoring, generation) runs in the worker via SQS, never inside
  an API request.
- The web app talks to the API only through `apps/web/lib/api.ts`.

## How to work on a feature

1. Plan first. Read the relevant section of `docs/architecture.md` and propose files, endpoints and tests.
2. Write or update tests first when the feature touches an invariant (see `tests/test_invariants.py`).
3. Implement in small steps. Run `make test` and `make lint`.
4. Review your own diff against the invariants above before finishing.

## Human review required

Auth, IAM and infra changes, data deletion, the approval and submission path, and any new job source.
Coding agents never get production credentials.
