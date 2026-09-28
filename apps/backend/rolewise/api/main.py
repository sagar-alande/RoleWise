import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rolewise.api.routers import documents, health, jobs, matches, profile
from rolewise.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="RoleWise API", version="0.1.0")

if get_settings().is_local:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(matches.router)
app.include_router(documents.router)
