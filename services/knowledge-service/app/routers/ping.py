from fastapi import APIRouter, Depends

from app.middleware.internal_auth import require_internal_token

# Temporary K0 endpoints. Deleted in K7 when real endpoints land.
public_router = APIRouter(prefix="/v1/knowledge")
internal_router = APIRouter(prefix="/internal")


@public_router.get("/ping")
async def public_ping() -> dict:
    return {"pong": True}


@internal_router.get("/ping", dependencies=[Depends(require_internal_token)])
async def internal_ping() -> dict:
    return {"pong": True}
