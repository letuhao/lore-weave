"""Test env defaults — set before app.config.Settings() loads at import time.

Matches the Dockerfile test-stage env (INTERNAL_SERVICE_TOKEN=test_token) so
the internal-auth header assertions line up.
"""

import os

os.environ.setdefault("COMPOSITION_DB_URL", "postgresql://u:p@h:5432/composition")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_token")
os.environ.setdefault("JWT_SECRET", "s" * 32)
