"""The X-Dev-User header bypasses real auth entirely and must only ever work when APP_ENV is
explicitly "local" - an unset or misconfigured APP_ENV must fail closed (require real auth), never
fail open (skip it). Regression for app_env defaulting to "local".

Tests here explicitly control APP_ENV via monkeypatch rather than relying on the ambient process
environment - the container this suite often runs in (docker exec into the running api service) has
a real APP_ENV=local already set for its own normal operation, which would otherwise mask exactly
the "unset/non-local" case this fix is about."""

from fastapi.testclient import TestClient

from rolewise.api.main import app
from rolewise.config import Settings, get_settings


def test_app_env_default_is_not_local():
    # The bare field default, independent of any env var this test process happens to have set -
    # this is what a container gets if APP_ENV is never configured at all.
    assert Settings.model_fields["app_env"].default != "local"


def test_settings_with_no_app_env_source_is_not_local(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    s = Settings(_env_file=None)  # bypass .env entirely - isolates the field default itself
    assert s.app_env != "local"
    assert s.is_local is False


def test_dev_user_header_is_ignored_when_app_env_is_not_local(monkeypatch):
    # A plain GET with no bearer token still needs to reach current_user() and fail there (401),
    # without ever touching the database - it must not depend on one being reachable.
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        resp = TestClient(app).get("/profile/facts", headers={"X-Dev-User": "attacker@example.com"})
        assert resp.status_code == 401
    finally:
        get_settings.cache_clear()


# The "still works when APP_ENV=local" side of this fix is intentionally NOT tested here: making
# that request succeed requires a real database write (current_user()'s _get_or_create()), and this
# file runs in the non-DB suite, which must never touch the database - the shared dev DB pollution
# that caused Phase 6C is exactly what that rule exists to prevent. That path is already covered
# end-to-end by the entire RUN_DB_TESTS=1 suite in test_e2e_db.py, whose `client` fixture explicitly
# sets APP_ENV=local and relies on X-Dev-User for every one of its tests against the isolated
# rolewise_test database.
