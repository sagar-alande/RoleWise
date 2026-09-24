"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE audit_log (
	id UUID NOT NULL,
	user_id UUID,
	actor VARCHAR(16) NOT NULL,
	action VARCHAR(100) NOT NULL,
	details JSONB NOT NULL,
	at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id)
)""",
    """CREATE INDEX ix_audit_log_user_id ON audit_log (user_id)""",
    """CREATE TABLE job_sources (
	id UUID NOT NULL,
	name VARCHAR(100) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	terms_ok BOOLEAN NOT NULL,
	config JSONB NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
)""",
    """CREATE TABLE users (
	id UUID NOT NULL,
	auth_subject VARCHAR(255) NOT NULL,
	email VARCHAR(320) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (auth_subject)
)""",
    """CREATE TABLE agent_runs (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	task VARCHAR(64) NOT NULL,
	status VARCHAR(32) NOT NULL,
	state JSONB NOT NULL,
	cost_usd FLOAT NOT NULL,
	error TEXT,
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	ended_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_agent_runs_user_id ON agent_runs (user_id)""",
    """CREATE TABLE career_facts (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	kind VARCHAR(32) NOT NULL,
	title VARCHAR(500) NOT NULL,
	details JSONB NOT NULL,
	source VARCHAR(32) NOT NULL,
	verified BOOLEAN NOT NULL,
	verified_at TIMESTAMP WITH TIME ZONE,
	embedding VECTOR(1024),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_career_facts_user_id ON career_facts (user_id)""",
    """CREATE TABLE jobs (
	id UUID NOT NULL,
	source_id UUID NOT NULL,
	external_id VARCHAR(255),
	company VARCHAR(255) NOT NULL,
	title VARCHAR(500) NOT NULL,
	location VARCHAR(255),
	remote_mode VARCHAR(16),
	salary_min INTEGER,
	salary_max INTEGER,
	description TEXT NOT NULL,
	url VARCHAR(2000),
	content_hash VARCHAR(64) NOT NULL,
	requirements_extracted BOOLEAN NOT NULL,
	embedding VECTOR(1024),
	posted_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (content_hash),
	FOREIGN KEY(source_id) REFERENCES job_sources (id)
)""",
    """CREATE TABLE preferences (
	user_id UUID NOT NULL,
	target_titles VARCHAR[] NOT NULL,
	locations VARCHAR[] NOT NULL,
	remote_modes VARCHAR[] NOT NULL,
	salary_min INTEGER,
	currency VARCHAR(3) NOT NULL,
	seniority VARCHAR(32),
	employment_types VARCHAR[] NOT NULL,
	industries VARCHAR[] NOT NULL,
	dealbreakers VARCHAR[] NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)""",
    """CREATE TABLE job_requirements (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	kind VARCHAR(32) NOT NULL,
	text TEXT NOT NULL,
	normalized VARCHAR(255),
	min_years FLOAT,
	embedding VECTOR(1024),
	PRIMARY KEY (id),
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_job_requirements_job_id ON job_requirements (job_id)""",
    """CREATE TABLE matches (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	job_id UUID NOT NULL,
	score FLOAT NOT NULL,
	breakdown JSONB NOT NULL,
	explanation JSONB,
	status VARCHAR(32) NOT NULL,
	model_version VARCHAR(100),
	prompt_version VARCHAR(50),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (user_id, job_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_matches_user_id ON matches (user_id)""",
    """CREATE TABLE approvals (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	match_id UUID NOT NULL,
	action VARCHAR(64) NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	approved_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_approvals_user_id ON approvals (user_id)""",
    """CREATE TABLE documents (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	match_id UUID,
	kind VARCHAR(32) NOT NULL,
	version INTEGER NOT NULL,
	content JSONB NOT NULL,
	s3_key VARCHAR(1024),
	status VARCHAR(32) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE SET NULL
)""",
    """CREATE INDEX ix_documents_user_id ON documents (user_id)""",
    """CREATE TABLE gap_analyses (
	match_id UUID NOT NULL,
	matched JSONB NOT NULL,
	partial JSONB NOT NULL,
	missing JSONB NOT NULL,
	underrepresented JSONB NOT NULL,
	recommendations JSONB NOT NULL,
	PRIMARY KEY (match_id),
	FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE
)""",
    """CREATE TABLE claims (
	id UUID NOT NULL,
	document_id UUID NOT NULL,
	text TEXT NOT NULL,
	supporting_fact_ids UUID[] NOT NULL,
	validator_status VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_claims_document_id ON claims (document_id)""",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for stmt in STATEMENTS:
        op.execute(stmt)
    # Approximate-nearest-neighbour indexes for vector recall.
    op.execute("CREATE INDEX ix_jobs_embedding ON jobs USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_career_facts_embedding ON career_facts USING hnsw (embedding vector_cosine_ops)")
    op.execute(
        "INSERT INTO job_sources (id, name, kind, terms_ok, config) "
        "VALUES (gen_random_uuid(), 'user_paste', 'user_paste', true, '{}'::jsonb)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claims")
    op.execute("DROP TABLE IF EXISTS gap_analyses")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS approvals")
    op.execute("DROP TABLE IF EXISTS matches")
    op.execute("DROP TABLE IF EXISTS job_requirements")
    op.execute("DROP TABLE IF EXISTS preferences")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS career_facts")
    op.execute("DROP TABLE IF EXISTS agent_runs")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS job_sources")
    op.execute("DROP TABLE IF EXISTS audit_log")
