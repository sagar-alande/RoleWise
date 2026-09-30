import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rolewise.api.routers import documents, health, jobs, matches, profile
from rolewise.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="RoleWise API", version="0.1.0")

_settings = get_settings()
# Local dev's origin is fixed (docker-compose always serves web on :3000). Everywhere else, the web
# app runs on a host only known at deploy time - see WEB_ORIGINS / config.py's web_origin_list and
# infra/README.md's deploy sequence for how that gets here. No origins configured means no
# cross-origin browser access at all, matching today's behavior before this app_env is redeployed
# with WEB_ORIGINS set, rather than silently allowing every origin.
_cors_origins = ["http://localhost:3000"] if _settings.is_local else _settings.web_origin_list
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(matches.router)
app.include_router(documents.router)
