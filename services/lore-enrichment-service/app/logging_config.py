"""Structured JSON logging for lore-enrichment-service (RAID C18).

Mirrors knowledge-service ``app/logging_config.py``: a single JSON stream
handler on the root logger with a ``trace_id`` / ``service`` context filter and
a secret-redaction filter. C18 adds ``job_id`` / ``stage`` correlation
ContextVars so a single enrichment job is followable end-to-end across the C14
runner's per-gap stages (gap-detect → retrieval → generate → verify → persist).

Invariants (C18 adversary focus "observability leaking secrets/PII"):
  * NO secrets / provider keys / bearer tokens in log lines — the
    :class:`RedactFilter` scrubs the common shapes regardless of caller.
  * NO model names are emitted by this module; the runner/strategies log
    model_ref ids (resolved via provider-registry), never model-name literals.
  * The correlation fields are bounded ids (job_id) + a closed stage vocab —
    never enriched CONTENT (the makeup lore lives in the quarantined proposal
    row, never in a log line).
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar

try:
    from pythonjsonlogger.json import JsonFormatter  # type: ignore
except ImportError:  # older python-json-logger
    from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore

#: Per-request trace id (set by TraceIdMiddleware). Empty outside a request.
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
#: Per-job correlation id (set by the C14 runner around a job). Empty otherwise.
job_id_var: ContextVar[str] = ContextVar("job_id", default="")
#: Current pipeline stage (gap-detect / retrieval / generate / verify / persist).
stage_var: ContextVar[str] = ContextVar("stage", default="")

_SERVICE_NAME = "lore-enrichment-service"

# Common secret shapes — scrub before the line is emitted. Same patterns as
# knowledge-service plus a generic api-key shape; defense-in-depth (the service
# already resolves secrets from env, never logs them, but a stray log of a
# request header or a provider error body must not leak a token).
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*\S+"),
]
_REDACTED = "***REDACTED***"

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(_REDACTED, text)
    return text


class RedactFilter(logging.Filter):
    """Scrub secret-shaped substrings from the message + string args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            try:
                record.args = tuple(
                    _redact(a) if isinstance(a, str) else a for a in record.args
                )
            except Exception:
                pass
        return True


class ContextFilter(logging.Filter):
    """Stamp every record with the service name + correlation ids."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = _SERVICE_NAME
        record.trace_id = trace_id_var.get() or ""
        record.job_id = job_id_var.get() or ""
        record.stage = stage_var.get() or ""
        return True


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _build_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(service)s "
        "%(trace_id)s %(job_id)s %(stage)s %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())
    handler.addFilter(RedactFilter())
    return handler


def setup_logging(level: str = "INFO") -> None:
    """Install the JSON handler on root + uvicorn loggers (idempotent)."""
    level_upper = level.upper()

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(_build_handler())
    root.setLevel(level_upper)

    # Uvicorn installs its own loggers with plain formatters; replace their
    # handlers so access/error logs flow through our JSON formatter too.
    for name in _UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(_build_handler())
        lg.setLevel(level_upper)
        lg.propagate = False
