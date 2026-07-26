from loreweave_authn import build_get_current_user

from app.config import settings

# Shared platform user-JWT verifier (loreweave_authn), replacing the inline
# HS256 `jwt.decode` block. `return_subject=True` preserves this service's
# existing shape: the raw `sub` string (interchangeable with
# `corrections.user_id`/`actor_id`, same auth-service identity domain as
# glossary/knowledge/chat). Secret is read lazily so a rotated secret is
# picked up without re-import.
get_current_user = build_get_current_user(
    lambda: settings.jwt_secret, return_subject=True
)
