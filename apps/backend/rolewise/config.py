from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_prompts_dir() -> Path:
    # Repo-relative fallback for running the API outside a container. Docker images set
    # PROMPTS_DIR explicitly (see Dockerfile, docker-compose.yml), which always wins over this.
    parents = Path(__file__).resolve().parents
    return parents[min(3, len(parents) - 1)] / "packages" / "prompts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Fail closed: an unset/misconfigured APP_ENV must never silently enable the X-Dev-User auth
    # bypass (see auth.py's current_user()) - local development always sets this explicitly via
    # docker-compose's env_file (.env), so this default is never actually relied on locally.
    app_env: str = "production"
    database_url: str = "postgresql+psycopg://rolewise:rolewise@localhost:5432/rolewise"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None  # LocalStack locally, None on AWS
    s3_public_endpoint_url: str | None = None  # endpoint the browser uses for presigned URLs (local only)
    s3_bucket: str = "rolewise-documents"
    sqs_queue_url: str = ""

    bedrock_enabled: bool = False
    bedrock_text_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_fast_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"
    embedding_dims: int = 1024

    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""

    prompts_dir: Path = Field(default_factory=_default_prompts_dir)

    # Matching configuration. Weights must sum to 1.0.
    # Components that have nothing to measure for a job are dropped and the rest renormalized.
    weight_required: float = 0.35
    weight_experience: float = 0.15
    weight_preferred: float = 0.10
    weight_domain: float = 0.05
    weight_education: float = 0.05
    weight_preferences: float = 0.10
    weight_north_star: float = 0.10  # fit with the user's target archetypes
    weight_level: float = 0.10  # job seniority vs the candidate's level
    match_threshold: float = 0.85
    partial_threshold: float = 0.65
    # Semantic fallback for "only show these roles": a job title whose embedding is at least this
    # close to a target role's embedding passes even with no shared words (e.g. "Data Platform
    # Engineer" for target "Data Engineer"). The literal adjacent-phrase check still passes on its
    # own below this. NOTE: with BEDROCK_ENABLED=false, the offline StubAI's embeddings only reflect
    # shared tokens, not real meaning - e.g. "Analytics Engineer" and "Software Engineer" score
    # identically (0.500) against "Data Engineer" since both just share the single word "Engineer".
    # 0.65 stays above that noise floor so irrelevant titles aren't admitted locally; real Bedrock
    # embeddings encode actual meaning, so this same threshold will correctly separate them there.
    title_semantic_threshold: float = 0.65

    # Job liveness (Phase 6B). Persisted listing_status only ever changes on source evidence from a
    # trusted refresh - these two control how aggressively that evidence is trusted, never how "stale"
    # is displayed (that's derived from last_checked_at at render time, not stored).
    stale_after_days: int = 7  # UI-only threshold for "not recently verified", never mutates listing_status
    suspicious_refresh_min_prior_count: int = 10  # boards below this size never trigger the guard
    suspicious_refresh_drop_ratio: float = 0.5  # a refresh returning under half the prior count is suspicious

    # On AWS the RDS secret is injected as separate fields (DB_SECRET is the JSON RDS secret).
    db_secret: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        if self.db_secret:
            import json
            from urllib.parse import quote_plus

            s = json.loads(self.db_secret)
            return (
                f"postgresql+psycopg://{s['username']}:{quote_plus(s['password'])}"
                f"@{s['host']}:{s.get('port', 5432)}/{s.get('dbname', 'rolewise')}"
            )
        return self.database_url

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
