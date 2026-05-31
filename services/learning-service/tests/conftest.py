"""Test env bootstrap — set required settings before app.config imports.

learning-service Settings() has required fields (no-hardcoded-secrets rule);
they must exist in the environment before `app.config` is imported at collection
time. TestClient is used WITHOUT a `with` block in tests so the lifespan (real
DB pool + Redis consumer) never runs — routes use dependency_overrides instead.
"""

import os

os.environ.setdefault("LEARNING_DB_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-token")
