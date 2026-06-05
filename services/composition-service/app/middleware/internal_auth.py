import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    if x_internal_token is None or not secrets.compare_digest(
        x_internal_token, settings.internal_service_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing internal service token",
        )
