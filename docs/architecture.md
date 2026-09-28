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

## Matching (modeled on career-ops, github.com/santifer/career-ops)

`services/matching.py` computes every score with fixed rules. The LLM only labels requirements (pass 1,
posting only) and explains results (after scoring). `services/signals.py` holds the deterministic checks.

1. **Hard filters** (job is not shown): dealbreakers (whole words), salary floor, target titles
   (`target_titles`), excluded title words, skipped seniority tiers. Missing data never filters a job.
2. **Requirements** (`job_requirements.v2`): each gets an importance band (critical, high, meaningful,
   preferred, low_signal), an evidence tier (stated, structural, inferred) and a verbatim quote when
   stated. An inferred requirement can never be critical or high. Importance weights credit inside a
   component (3, 2, 1, 0.5, 0.25).
3. **Components and weights** (`rolewise/config.py`): required 0.35, experience 0.15, preferred 0.10,
   domain 0.05, education 0.05, preferences 0.10, north_star (archetype fit) 0.10, level 0.10.
   Components with nothing to measure are dropped and the rest renormalized.
   Requirement thresholds: similarity >= 0.85 matched, >= 0.65 partial, otherwise missing.
4. **Signals**: work authorization (sponsors, not_needed, unstated, no_sponsorship) and geo mismatch
   (remote listing that requires office days). Only no_sponsorship is a hard stop, which caps the global
   score at 2.5. Flags never change the score.
5. **Global score and verdict**: global = 1 + 4 x score/100. apply_now >= 4.5, worth_applying >= 4.0,
   only_with_reason >= 3.5, otherwise not_recommended. A hard stop gives verdict hard_stop.
6. **Gaps**: every missing or partial critical/high requirement gets an interview risk and a mitigation.

When preferences change, jobs that no longer pass are marked `verdict = "filtered"` and hidden.

## Tailored documents (modeled on career-ops modes/pdf.md and modes/cover.md)

"Get documents" on a match (`POST /matches/{id}/documents`) saves the job to My jobs and queues
`generate_documents`. The worker sends the job, its ranked requirements and the user's verified facts (ids,
titles, details) to `resume_tailor.v1` and `cover_letter.v1`. The model may select, reorder and reword, and
must cite fact ids for every line.

`services/documents.py` then fact-checks every line: cited ids must be verified facts, every number must
appear in the cited facts (or be the sum of cited role years), and every skill or requirement term must
appear in the cited facts. Failing lines are removed and shown to the user with the reason. Role, education
and certification headers are rendered from the facts, never from model text. Each run stores a new
`documents` version with its `claims`, so earlier versions stay available. Downloads: DOCX and Markdown
(`GET /documents/{id}/download`), and a print stylesheet for Save as PDF.

## Tables

users (with contact details), career_facts, preferences, job_sources, jobs, job_requirements, matches, gap_analyses,
documents, claims, approvals, agent_runs, audit_log. See `apps/backend/rolewise/models.py`.
