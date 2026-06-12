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
def _e0_grant_gate_shim(monkeypatch):
    """E0-3 test shim — make the collaboration access gate transparent for the
    router unit tests (which exercise routes AS THE OWNER and assert cross-user
    denial via the fake repo's own ``user_id`` filtering).

    Router unit tests build their own ``FastAPI()`` and ``include_router`` inside a
    fixture (no book-service to resolve grants against). We patch ``include_router``
    so every freshly-built app gets the gate's overridable deps stubbed:
      - ``project_meta_dep``/``job_meta_dep`` → ``(caller, None)`` so ``caller==owner``
        always passes — the gate becomes a pass-through and the fake repo still
        returns the real cross-user 404 (behavior identical to pre-E0-3), and
      - ``get_grant_client`` → an owner-level stub for book-scoped routes (raw-search).

    ``setdefault`` is used so a test that asserts the REAL grant logic (a
    collaborator / a denial) can override these with specific values in its body
    and win. The app.main singleton (used by integration tests) includes its
    routers at import — before this shim — so it is unaffected.
    """
    from fastapi import Depends, FastAPI

    from app.auth.grant_deps import job_meta_dep, project_meta_dep
    from app.clients.grant_client import GrantLevel
    from app.deps import get_grant_client
    from app.middleware.jwt_auth import get_current_user

    async def _meta(caller=Depends(get_current_user)):
        return (caller, None)

    class _OwnerGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER

        async def resolve_access(self, book_id, user_id):
            return (GrantLevel.OWNER, "active")

    _orig_include = FastAPI.include_router

    def _patched_include(self, router, *args, **kwargs):
        result = _orig_include(self, router, *args, **kwargs)
        self.dependency_overrides.setdefault(project_meta_dep, _meta)
        self.dependency_overrides.setdefault(job_meta_dep, _meta)
        self.dependency_overrides.setdefault(get_grant_client, lambda: _OwnerGrant())
        return result

    monkeypatch.setattr(FastAPI, "include_router", _patched_include)

    # Tests that use the app.main singleton (routers already included at import,
    # before the patch above) need the overrides set directly on it. setdefault so
    # a test's explicit override wins; pop on teardown (a test's own .clear() may
    # have removed them already — pop is then a no-op).
    from app.main import app as _singleton
    for dep, val in (
        (project_meta_dep, _meta),
        (job_meta_dep, _meta),
        (get_grant_client, lambda: _OwnerGrant()),
    ):
        _singleton.dependency_overrides.setdefault(dep, val)
    yield
    for dep in (project_meta_dep, job_meta_dep, get_grant_client):
        _singleton.dependency_overrides.pop(dep, None)


@pytest.fixture(autouse=True)
def _clear_context_cache():
    """K6.2: the TTL cache is a module-level singleton. Clear it
    between tests so earlier tests don't hide a repo miss in a
    later test via a stale cache entry.

    K6-I4: also reset the module-level circuit_open gauge so a
    test that trips a breaker doesn't leave the gauge at 1 for
    the next test's metrics assertions.
    """
    from app.context import cache
    from app.metrics import circuit_open
    cache.clear_all()
    circuit_open.labels(service="glossary").set(0)
    yield
    cache.clear_all()
    circuit_open.labels(service="glossary").set(0)
