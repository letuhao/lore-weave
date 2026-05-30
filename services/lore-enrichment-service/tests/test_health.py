import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_health_ok(monkeypatch):
    # /health must not require a live DB. Stub the pool so the lifespan
    # startup (create_pool) doesn't dial a real postgres during the test.
    import app.db.pool as pool_mod
    import app.main as main_mod

    async def _fake_create_pool(dsn):
        return object()

    async def _fake_close_pool():
        return None

    async def _fake_run_migrations(pool):
        # /health must not require a live DB; C2 added run_migrations to the
        # lifespan, so stub it too (the real DDL is exercised in tests/db/).
        return None

    # main.py imported create_pool/close_pool/run_migrations by name at module
    # load, so patch the names it actually calls (the module globals), plus the
    # source modules.
    monkeypatch.setattr(main_mod, "create_pool", _fake_create_pool)
    monkeypatch.setattr(main_mod, "close_pool", _fake_close_pool)
    monkeypatch.setattr(main_mod, "run_migrations", _fake_run_migrations)
    monkeypatch.setattr(pool_mod, "create_pool", _fake_create_pool)
    monkeypatch.setattr(pool_mod, "close_pool", _fake_close_pool)

    with TestClient(main_mod.app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.text == "ok"


def test_config_fail_fast_on_missing_secret(monkeypatch, tmp_path):
    # Adversary r1 WARN#2: env_file=".env" resolves from CWD — a stray .env would
    # make Settings() succeed and turn this test false-green. Isolate hard:
    # clear the env vars, chdir to an empty tmp dir, and disable env_file.
    from pydantic import ValidationError

    from app.config import Settings

    for var in ("LORE_ENRICHMENT_DB_URL", "JWT_SECRET", "INTERNAL_SERVICE_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_config_fail_fast_crashes_import():
    # Adversary r2 WARN#3: the REAL production fail-fast is the module-level
    # `settings = Settings()` in app/config.py — a missing required secret must
    # crash *import* so the container won't start. Prove it in a subprocess with
    # the required vars cleared (the in-process Settings() test above can't,
    # because conftest pre-populated os.environ for collection).
    svc_root = Path(__file__).resolve().parents[1]
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("LORE_ENRICHMENT_DB_URL", "JWT_SECRET", "INTERNAL_SERVICE_TOKEN")
    }
    env["PYTHONPATH"] = str(svc_root)
    proc = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=str(svc_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, (
        "import app.config must fail-fast when required secrets are missing; "
        f"got rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "validation error" in (proc.stdout + proc.stderr).lower()
