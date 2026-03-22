import time
import jwt


def mint_user_jwt(user_id: str, jwt_secret: str, ttl_seconds: int = 300) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def verify_request_jwt(token: str, jwt_secret: str) -> str:
    """Validate incoming Bearer token, return user_id (sub claim)."""
    data = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    return data["sub"]
