import os

# `app.config` instantiates `Settings()` at import time (fail-fast). Tests must
# supply the required secrets BEFORE any `import app.*` so collection doesn't
# blow up. These are throwaway test values, never real credentials.
os.environ.setdefault("LORE_ENRICHMENT_DB_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test_jwt_secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_internal_token")
