"""Authentication. Cognito JWTs in AWS. A dev header only when APP_ENV=local."""

from __future__ import annotations

import logging
import time

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from rolewise.aws import cognito_idp
from rolewise.config import get_settings
from rolewise.db import get_db
from rolewise.models import User

log = logging.getLogger(__name__)

_jwks_cache: dict = {"keys": None, "fetched": 0.0}


def _issuer() -> str:
    s = get_settings()
    return f"https://cognito-idp.{s.aws_region}.amazonaws.com/{s.cognito_user_pool_id}"


def _jwks() -> list[dict]:
    if not _jwks_cache["keys"] or time.time() - _jwks_cache["fetched"] > 3600:
        resp = httpx.get(f"{_issuer()}/.well-known/jwks.json", timeout=5)
        resp.raise_for_status()
        _jwks_cache.update(keys=resp.json()["keys"], fetched=time.time())
    return _jwks_cache["keys"]


def _verify_token(token: str) -> dict:
    s = get_settings()
    try:
        kid = jwt.get_unverified_header(token)["kid"]
        key = next(k for k in _jwks() if k["kid"] == kid)
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=_issuer(), options={"verify_aud": False})
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    # Cognito access tokens carry client_id, id tokens carry aud.
    if claims.get("client_id", claims.get("aud")) != s.cognito_app_client_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong client")
    return claims


def _fetch_cognito_email(access_token: str) -> str:
    """Cognito ACCESS tokens never carry an email claim (only ID tokens do), so the sub alone isn't
    enough to learn a federated user's email. GetUser takes the caller's own access token - no admin
    credentials needed - and returns their attributes, same pattern as the token itself."""
    try:
        resp = cognito_idp().get_user(AccessToken=access_token)
        return next((a["Value"] for a in resp.get("UserAttributes", []) if a["Name"] == "email"), "")
    except Exception:
        log.exception("Could not fetch email from Cognito for a new or incomplete user")
        return ""


def _get_or_create(db: Session, subject: str, access_token: str | None, fallback_email: str = "") -> User:
    user = db.scalar(select(User).where(User.auth_subject == subject))
    if user and user.email:
        return user
    email = fallback_email or (_fetch_cognito_email(access_token) if access_token else "")
    if not user:
        user = User(auth_subject=subject, email=email)
        db.add(user)
        db.commit()
    elif email:
        user.email = email
        db.commit()
    return user


def current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
) -> User:
    s = get_settings()
    if s.is_local and x_dev_user:
        return _get_or_create(db, f"dev:{x_dev_user}", access_token=None, fallback_email=x_dev_user)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    claims = _verify_token(token)
    return _get_or_create(db, claims["sub"], access_token=token, fallback_email=claims.get("email", ""))
