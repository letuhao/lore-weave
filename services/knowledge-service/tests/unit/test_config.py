import os
import subprocess
import sys
import textwrap

# Keys the subprocess needs to import Python + app.config. We pass no other
# env so the test truly controls which Settings fields are set.
_INHERIT_KEYS = (
    "PATH",
    "PYTHONPATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
)


def _base_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _INHERIT_KEYS if k in os.environ}
    # Force pytest's working dir onto PYTHONPATH so `import app` works.
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run_isolated(extra: dict[str, str]) -> subprocess.CompletedProcess:
    """Run a fresh Python process so we get pristine import state.

    Using importlib.reload within the same process leaks state into
    app.middleware.internal_auth (which captured `from app.config import
    settings` at first import). Subprocess isolation avoids that entirely.
    """
    code = textwrap.dedent(
        """
        import sys
        try:
            from app.config import Settings
            Settings()
        except Exception as exc:
            print(type(exc).__name__, file=sys.stderr)
            sys.exit(2)
        print("ok")
        """
    )
    env = _base_env()
    env.update(extra)
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )


def test_missing_required_raises():
    # No Settings env vars → Settings() must fail.
    result = _run_isolated(extra={})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "ValidationError" in result.stderr


def test_all_required_present():
    result = _run_isolated(
        extra={
            "KNOWLEDGE_DB_URL": "postgresql://u:p@h:5432/db",
            "GLOSSARY_DB_URL": "postgresql://u:p@h:5432/db",
            "INTERNAL_SERVICE_TOKEN": "tok",
            "JWT_SECRET": "s" * 32,
        }
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_settings_defaults():
    # Loaded via conftest.py env — verify defaults are as documented.
    from app.config import settings

    assert settings.port == 8092
    assert settings.log_level == "INFO"
    assert settings.redis_url.startswith("redis://")
