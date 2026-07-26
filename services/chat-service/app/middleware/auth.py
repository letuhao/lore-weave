from loreweave_authn import build_get_current_user

from app.config import settings

# Platform user JWT verifier, migrated to the shared SDK (loreweave_authn).
# return_subject=True preserves chat-service's historical shape: the dependency
# returns the `sub` STRING (a UUID-as-string), not a UUID object.
get_current_user = build_get_current_user(lambda: settings.jwt_secret, return_subject=True)
