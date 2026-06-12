from fastapi import APIRouter, Depends

from app.middleware.internal_auth import require_internal_token

# M0 liveness endpoints. Real /v1/composition/* endpoints land M2–M6.
public_router = APIRouter(prefix="/v1/composition")
internal_router = APIRouter(prefix="/internal")


@public_router.get("/ping")
async def public_ping() -> dict:
    return {"pong": True}


@internal_router.get("/ping", dependencies=[Depends(require_internal_token)])
async def internal_ping() -> dict:
    return {"pong": True}
