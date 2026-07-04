import time
import jwt

# P3 (SDK-first): the hand-rolled `verify_request_jwt` was removed — every user-JWT
# VERIFY now goes through the shared `loreweave_authn` SDK (the request path uses
# `deps.get_current_user`; the confirm-replay path uses `verify_access_token`
# directly). Only the short-lived internal MINTER remains here (not a verifier).


def mint_user_jwt(user_id: str, jwt_secret: str, ttl_seconds: int = 300) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, jwt_secret, algorithm="HS256")
