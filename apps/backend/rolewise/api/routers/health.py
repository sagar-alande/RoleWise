from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Used by the ECS Express Mode load balancer health check."""
    return {"status": "ok"}
