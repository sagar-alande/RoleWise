# RoleWise

<p align="center"><strong>An AI career agent that never speaks for you.</strong><br>
It reads your resume, matches you to real job postings, explains every score, and tells you exactly
where you fall short — using only facts you've verified, never facts it invented.</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-capstone_project-orange" alt="Capstone project">
  <img src="https://img.shields.io/badge/AIML--515-IWU_AI_Integration_Capstone-blue" alt="AIML-515">
</p>

<p align="center"><sub>Built for AIML-515: AI Integration Capstone, Indiana Wesleyan University.<br>
This is coursework, not a hosted product — see <a href="#about">About</a>.</sub></p>

---

## What RoleWise does

- **Verifies before it trusts.** Every fact about you — a role, a skill, a degree — starts as
  `unverified` when parsed from a resume. Nothing is used to match or write documents until you confirm it.
- **Scores jobs with fixed rules, not vibes.** `services/matching.py` computes every match score
  deterministically (required/experience/preferred/domain/education/preference/level weights). The LLM
  only labels requirement importance and writes the plain-English explanation *after* the score exists —
  it never sets the number.
- **Shows you the gap, not just the score.** For every missing or partial requirement that matters, it
  names the interview risk and a concrete way to close it.
- **Drafts tailored resumes and cover letters — then fact-checks its own output.** Every generated line
  must cite a verified fact by id. Every number and every named skill must trace back to that citation.
  Lines that don't survive the check are stripped out and flagged, not silently kept.
- **Flags hard blockers instead of hiding them.** No-sponsorship postings and remote-vs-office mismatches
  are called out explicitly rather than folded into the score.

## What RoleWise will not do

- **Fabricate your experience.** The tailoring prompt can reorder, select and reword — it cannot invent a
  role, a skill, or a number that isn't in your verified facts. A [`FactChecker`](apps/backend/rolewise/services/documents.py)
  pass enforces this on every generated document, not just the prompt instructions.
- **Submit anything on your own behalf.** There is no "apply" button that sends data anywhere. Documents
  are generated for you to read and download (DOCX/Markdown); you decide what to do with them.
- **Phone home with your data.** Your resume and facts live in your own Postgres database and S3 bucket.
  Local dev never touches AWS at all — `BEDROCK_ENABLED=false` returns deterministic stub output.
- **Trust an unset environment.** Auth fails closed: an unconfigured `APP_ENV` can never fall back to the
  local dev-auth bypass. See [Security](#security-notes).

## Features

| Feature | Description |
| --- | --- |
| **Verified-fact profile** | Resume parsing (PDF, ≤10MB, ≤20 pages) extracts candidate facts as `unverified`; you edit, verify, or delete each one before it's used anywhere |
| **Explainable matching** | Deterministic scoring engine (`matching.py`) with per-requirement importance bands, evidence tiers (stated/structural/inferred), and a similarity-based matched/partial/missing classifier (`gaps.py`) |
| **Job ingestion** | Public ATS APIs only — Greenhouse, Lever, Ashby board feeds, plus paste-a-URL or paste-a-description for a single job. No scraping of sites whose terms forbid it |
| **Gap analysis** | Every unmet critical/high requirement gets a named interview risk and a mitigation suggestion |
| **Fact-checked document generation** | Tailored resume + narrative cover letter, versioned per run, every claim traceable to a cited fact id; DOCX and Markdown downloads |
| **Work-auth & location signals** | No-sponsorship and remote/office mismatches surfaced as explicit flags, not buried in the score |
| **Google Sign-In** | Cognito Hosted UI + Authorization Code + PKCE — no secrets ever reach the browser |
| **Recommendation dashboard** | Ranked matches, saved "My jobs," per-match detail view with the full score breakdown |

## How it works

```
Resume upload (S3, presigned URL)
        │
        ▼
┌────────────────────┐
│  Extraction         │  resume_extract.v2 → CareerFacts, verified=false
│  (worker)           │
└─────────┬───────────┘
          │  you review + verify facts in the UI
          ▼
┌────────────────────┐     ┌──────────────────────┐
│  Job ingestion       │───▶│  Requirement labeling │  job_requirements.v2:
│  (Greenhouse/Lever/  │    │  + embedding          │  importance band, evidence tier
│  Ashby / paste)      │    └──────────┬────────────┘
└────────────────────┘                │
                                        ▼
                              ┌──────────────────────┐
                              │  Deterministic scoring│  matching.py + signals.py
                              │  + hard filters       │  (fixed rules, no LLM)
                              └──────────┬────────────┘
                                          ▼
                              ┌──────────────────────┐
                              │  Gap analysis + LLM   │  gaps.py classifies;
                              │  explanation           │  match_explanation.v1 writes it
                              └──────────┬────────────┘
                                          ▼
                                  Recommendation dashboard
                                          │
                              "Get documents" on a match
                                          ▼
                              ┌──────────────────────┐
                              │  Tailor + fact-check   │  resume_tailor.v1 / cover_letter.v1
                              │  (documents.py)        │  → every line cited, checked, versioned
                              └──────────┬────────────┘
                                          ▼
                                 DOCX / Markdown download
```

Full request-flow detail (matching weights, thresholds, verdict bands) is in
[docs/architecture.md](docs/architecture.md).

## Quick start (local)

Requirements: Docker Desktop, Node 20+, Python 3.11+.

```bash
cp .env.example .env
make up          # starts postgres (pgvector), localstack, api, worker, web
make migrate      # creates tables
```

- Web: http://localhost:3000
- API docs: http://localhost:8000/docs

Local mode uses `BEDROCK_ENABLED=false`, so AI calls return deterministic stubs and no AWS account is
needed. Set `BEDROCK_ENABLED=true` with real AWS credentials to call Bedrock instead.

Local auth: when `APP_ENV=local`, send the header `X-Dev-User: you@example.com` instead of a Cognito
token — the web app does this automatically. `APP_ENV` defaults to `production` everywhere else, so this
bypass can never activate by accident (see [Security notes](#security-notes)).

## Project structure

```
RoleWise/
├── CLAUDE.md                 # Agent instructions (Cursor mirror in .cursor/rules)
├── docs/
│   ├── architecture.md       # Request flows, scoring weights, data model
│   └── adr/                  # Architecture decision records
├── apps/
│   ├── web/                  # Next.js 15 + React 19 frontend
│   └── backend/
│       └── rolewise/
│           ├── api/routers/  # jobs, matches, profile, documents, health
│           ├── services/     # matching, gaps, signals, documents (fact-checker)
│           ├── worker/       # SQS consumer: parse_resume, ingest, score_matches, generate_documents
│           ├── auth.py       # Cognito JWT verification + local dev-header bypass
│           └── config.py     # Settings (fail-closed defaults)
├── packages/prompts/          # Versioned LLM prompts (resume_extract.v2, job_requirements.v2, ...)
├── evals/                     # Golden datasets and evaluation scripts
├── infra/                     # AWS CDK stack (ECS Express Mode, RDS, S3, SQS, Cognito)
├── .github/workflows/          # CI and deploy pipelines
└── docker-compose.yml          # Full local stack
```

## Security notes

Written up in more detail in the course deliverables, but the short version of what's actually enforced
in code today:

- **Fail-closed dev auth.** `Settings.app_env` defaults to `"production"`; the `X-Dev-User` header bypass
  only works when `APP_ENV` is explicitly `"local"` — never on an unset or misconfigured value.
- **Resume upload limits.** 10MB max file size (checked via an S3 `HEAD` before download) and a 20-page
  cap on PDF parsing, both rejected with a friendly message rather than exhausting the worker.
- **Prompt-injection guardrails.** Every prompt that interpolates resume or job-posting text explicitly
  tells the model that text is untrusted data, not instructions.
- **No raw errors to users.** Backend and frontend both collapse unexpected exceptions into a generic
  message; full detail goes to logs only.

Deferred, tracked, and intentionally not yet fixed: S3 bucket CORS origin scoping and the worker's S3 IAM
grant are broader than they need to be.

## Deployment

Services run on Amazon ECS Express Mode. See [docs/architecture.md](docs/architecture.md) for the service
map and [infra/README.md](infra/README.md) for the CDK stack and first-deploy steps.

## Tech stack

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js_15-000?style=flat&logo=next.js&logoColor=white)
![React](https://img.shields.io/badge/React_19-61DAFB?style=flat&logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16_%2B_pgvector-4169E1?style=flat&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy_2-D71F00?style=flat)
![AWS](https://img.shields.io/badge/AWS_ECS_%7C_S3_%7C_SQS_%7C_Cognito-232F3E?style=flat&logo=amazonaws&logoColor=white)
![Bedrock](https://img.shields.io/badge/Amazon_Bedrock-232F3E?style=flat&logo=amazonaws&logoColor=white)
![CDK](https://img.shields.io/badge/AWS_CDK-527FFF?style=flat&logo=amazonwebservices&logoColor=white)
![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat&logo=docker&logoColor=white)

- **API**: FastAPI + SQLAlchemy 2 + Alembic, Cognito JWT auth
- **Worker**: SQS consumer, same codebase as the API (two entrypoints, one image)
- **AI**: Amazon Bedrock in production, a deterministic offline stub in local dev — same interface
  (`get_ai()`), so no code branches on which one is running
- **Data**: RDS PostgreSQL 16 with pgvector for requirement-embedding recall
- **Frontend**: Next.js 15 App Router, React 19, TypeScript, Tailwind 4
- **Infra**: AWS CDK — ECS Express Mode (web/api), Fargate (worker), S3, SQS with a DLQ, Cognito

## About

RoleWise is the capstone project for **AIML-515: AI Integration Capstone** at Indiana Wesleyan University
(instructor: Dr. Steward Huang; author: Sagar Shirishkumar Alande). It's a working system, not a demo
shell — but it's coursework, actively iterated on with an AI coding assistant, and the repository is kept
private because it contains the author's real contact details and in-progress academic work.

The matching engine and document-tailoring pipeline are explicitly modeled on the design of
[career-ops](https://github.com/career-ops-hq/career-ops) — a human-in-the-loop, fact-grounded job-search
tool — adapted here into RoleWise's own web app + API + worker architecture rather than a CLI skill.
