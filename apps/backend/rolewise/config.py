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

    app_env: str = "local"
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
    weight_required: float = 0.40
    weight_experience: float = 0.20
    weight_preferred: float = 0.15
    weight_domain: float = 0.10
    weight_education: float = 0.05
    weight_preferences: float = 0.10
    match_threshold: float = 0.85
    partial_threshold: float = 0.65

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
