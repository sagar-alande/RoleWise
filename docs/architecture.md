# RoleWise architecture

The full design (problem framing, features, roadmap) is in the shared design doc
"RoleWise: AI Career Agent Design". This file is the short version agents read before coding.

## Services

| Service | Code | Runs on | Purpose |
| --- | --- | --- | --- |
| web | `apps/web` | ECS Express Mode | Next.js UI |
| api | `apps/backend` (`rolewise.api.main:app`) | ECS Express Mode | REST API, auth, enqueues tasks |
| worker | `apps/backend` (`rolewise.worker.main`) | ECS Fargate service | SQS consumer for AI tasks |

Data: RDS PostgreSQL 16 + pgvector, S3 for documents, SQS for tasks, Cognito for auth, Bedrock for AI.

## Request flow: resume upload

1. `POST /profile/resume/upload-url` returns a presigned S3 URL. The browser uploads directly to S3.
2. `POST /profile/resume/parse` enqueues `parse_resume`.
3. The worker extracts text, calls Bedrock with `resume_extract.v1`, and stores facts with `verified=false`.
4. The user confirms facts in the UI (`POST /profile/facts/{id}/verify`). Only verified facts are used.

## Request flow: matching

1. The worker ingests jobs (`ingest_greenhouse_board` or `POST /jobs/paste`), dedups by content hash,
   extracts requirements with `job_requirements.v1`, and embeds each requirement.
2. `score_matches` runs for the user: preference filters, pgvector recall, then
   `services/matching.py` computes a deterministic score and breakdown.
3. `services/gaps.py` classifies matched, partial, missing and underrepresented requirements.
4. The LLM writes the explanation from the breakdown using `match_explanation.v1`.

## Scoring weights (config, `rolewise/config.py`)

required skills 0.40, experience 0.20, preferred skills 0.15, domain 0.10, education 0.05, preferences 0.10.
Requirement thresholds: similarity >= 0.85 matched, >= 0.65 partial, otherwise missing.

## Tables

users, career_facts, preferences, job_sources, jobs, job_requirements, matches, gap_analyses,
documents, claims, approvals, agent_runs, audit_log. See `apps/backend/rolewise/models.py`.
