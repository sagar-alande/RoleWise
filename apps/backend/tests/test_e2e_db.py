"""End-to-end flow against a real Postgres + pgvector. Runs when RUN_DB_TESTS=1 (CI sets it).

Without SQS_QUEUE_URL, tasks run inline, so the whole pipeline executes in one process.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="needs Postgres (RUN_DB_TESTS=1)")

JOB_TEXT = (
    "We are hiring a backend engineer. Required: Python, PostgreSQL, Docker and AWS. "
    "You need 3 years of professional experience building REST API services. Remote friendly."
)


@pytest.fixture()
def client(monkeypatch):
    from rolewise.config import get_settings

    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()
    from rolewise.api.main import app

    yield TestClient(app, headers={"X-Dev-User": f"{uuid.uuid4()}@example.com"})
    get_settings.cache_clear()


def test_profile_to_explained_match(client):
    for kind, title, details in [
        ("skill", "python", {}),
        ("skill", "postgresql", {}),
        ("skill", "docker", {}),
        ("role", "Backend Developer at Initech", {"years": 4}),
    ]:
        assert client.post("/profile/facts", json={"kind": kind, "title": title, "details": details}).status_code == 201

    client.put("/profile/preferences", json={"remote_modes": ["remote"], "dealbreakers": []})

    resp = client.post("/jobs/paste", json={
        "company": f"Acme {uuid.uuid4().hex[:6]}", "title": "Backend Engineer",
        "description": JOB_TEXT, "remote_mode": "remote",
    })
    assert resp.status_code == 202
    assert client.get(f"/profile/runs/{resp.json()['run_id']}").json()["status"] == "done"

    assert client.post("/matches/refresh").status_code == 202
    matches = client.get("/matches").json()
    assert matches, "expected at least one match"
    top = client.get(f"/matches/{matches[0]['id']}").json()

    statuses = {r["text"]: r["status"] for r in top["breakdown"]["requirements"]}
    assert statuses["python"] == "matched"
    assert statuses["aws"] == "missing"
    assert top["explanation"]["summary"]
    assert sorted(g["text"] for g in top["gaps"]["missing"]) == ["aws", "rest api"]
    assert statuses["3 years"] == "matched"  # 4 verified years on the role fact
    assert 0 < top["score"] < 100
