import os

# Populate required env vars BEFORE any `app.*` import. Pytest imports test
# modules at collection time; without these, `from app.config import settings`
# would raise during collection.
os.environ.setdefault("KNOWLEDGE_DB_URL", "postgresql://u:p@h:5432/knowledge")
os.environ.setdefault("GLOSSARY_DB_URL", "postgresql://u:p@h:5432/glossary")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "default_test_token")
os.environ.setdefault("JWT_SECRET", "s" * 32)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_context_cache():
    """K6.2: the TTL cache is a module-level singleton. Clear it
    between tests so earlier tests don't hide a repo miss in a
    later test via a stale cache entry."""
    from app.context import cache
    cache.clear_all()
    yield
    cache.clear_all()
