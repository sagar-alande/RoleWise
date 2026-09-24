"""AI access layer. BedrockAI calls Amazon Bedrock. StubAI is deterministic and offline for local dev and tests.

Everything else in the codebase calls get_ai() and never talks to Bedrock directly.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from typing import Protocol

from rolewise.config import get_settings
from rolewise.services.prompts import render_prompt


class AI(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def complete_json(self, prompt_name: str, fast: bool = False, **variables: str) -> tuple[dict, str]:
        """Returns (parsed JSON, model id)."""
        ...


def _parse_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


class BedrockAI:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.settings = s
        self.client = boto3.client("bedrock-runtime", region_name=s.aws_region)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            body = json.dumps({"inputText": text[:8000], "dimensions": self.settings.embedding_dims, "normalize": True})
            resp = self.client.invoke_model(modelId=self.settings.bedrock_embed_model_id, body=body)
            vectors.append(json.loads(resp["body"].read())["embedding"])
        return vectors

    def complete_json(self, prompt_name: str, fast: bool = False, **variables: str) -> tuple[dict, str]:
        model_id = self.settings.bedrock_fast_model_id if fast else self.settings.bedrock_text_model_id
        prompt = render_prompt(prompt_name, **variables)
        resp = self.client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0},
        )
        text = resp["output"]["message"]["content"][0]["text"]
        return _parse_json(text), model_id


# --------------------------------------------------------------------------- offline stub

# Vocabulary so the stub can "extract" skills from text via keyword matching. It's necessarily
# shallow next to real extraction (Bedrock reads the whole description); this list exists to make
# local/offline dev and demos closer to real results, not to replace the LLM path.
KNOWN_SKILLS = [
    # languages
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++", "c#", "ruby",
    "scala", "kotlin", "swift", "php", "r",
    # web / app frameworks
    "react", "next.js", "vue", "angular", "node.js", "fastapi", "django", "flask", "spring",
    "ruby on rails", "graphql", "rest api", "grpc",
    # data / ml
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "snowflake", "bigquery",
    "machine learning", "deep learning", "pytorch", "tensorflow", "scikit-learn", "nlp", "llm",
    "data analysis", "data engineering", "pandas", "numpy", "spark", "airflow", "dbt", "etl",
    "tableau", "power bi", "looker", "excel", "a/b testing", "statistics",
    # cloud / infra
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ci/cd", "linux", "microservices",
    "distributed systems", "system design",
    # product / design
    "figma", "sketch", "product management", "roadmapping", "user research", "prototyping",
    "wireframing", "a/b tests", "ux research", "design systems",
    # business / ops / legal
    "salesforce", "hubspot", "sql reporting", "financial modeling", "forecasting", "contract negotiation",
    "compliance", "gdpr", "sox", "vendor management", "budget management", "recruiting",
    # general / soft skills
    "git", "agile", "scrum", "kanban", "project management", "stakeholder management",
    "communication", "leadership", "mentoring", "cross-functional collaboration",
]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#./]+", text.lower())


def _stub_vector(text: str, dims: int) -> list[float]:
    """Bag-of-tokens hashed into a unit vector. Shared words give positive cosine similarity."""
    vec = [0.0] * dims
    for tok in _tokens(text):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        vec[h % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _find_skills(text: str) -> list[str]:
    low = text.lower()
    return [s for s in KNOWN_SKILLS if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", low)]


class StubAI:
    model_id = "stub-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        dims = get_settings().embedding_dims
        return [_stub_vector(t, dims) for t in texts]

    def complete_json(self, prompt_name: str, fast: bool = False, **variables: str) -> tuple[dict, str]:
        base = prompt_name.split(".")[0]
        if base == "resume_extract":
            skills = _find_skills(variables.get("resume_text", ""))
            return {"facts": [{"kind": "skill", "title": s, "details": {}} for s in skills]}, self.model_id
        if base == "job_requirements":
            text = variables.get("job_description", "")
            # Anything after "nice to have" / "preferred" / "bonus" counts as preferred.
            parts = re.split(r"nice to have|preferred|bonus", text, maxsplit=1, flags=re.IGNORECASE)
            required = _find_skills(parts[0])
            preferred = [s for s in _find_skills(parts[1])] if len(parts) > 1 else []
            years = re.search(r"(\d+)\+?\s+years", text)
            reqs = [{"kind": "required_skill", "text": s, "normalized": s} for s in required]
            reqs += [{"kind": "preferred_skill", "text": s, "normalized": s} for s in preferred if s not in required]
            if years:
                reqs.append({"kind": "experience", "text": years.group(0), "min_years": float(years.group(1))})
            return {"requirements": reqs}, self.model_id
        if base == "match_explanation":
            b = json.loads(variables.get("breakdown_json", "{}"))
            matched = [r["fact_title"] for r in b.get("requirements", [])
                       if r["status"] == "matched" and r.get("fact_title")]
            missing = [r["text"] for r in b.get("requirements", []) if r["status"] == "missing"]
            n_matched = sum(1 for r in b.get("requirements", []) if r["status"] == "matched")
            return {
                "summary": f"Score {b.get('score', 0):.0f}. You match {n_matched} requirements "
                f"and are missing {len(missing)}.",
                "strengths": [f"Verified experience with {m}" for m in matched[:5]],
                "gaps": [f"No verified evidence of {m}" for m in missing[:5]],
                "resume_tips": [],
            }, self.model_id
        raise ValueError(f"StubAI has no handler for prompt {prompt_name}")


@lru_cache
def get_ai() -> AI:
    return BedrockAI() if get_settings().bedrock_enabled else StubAI()
