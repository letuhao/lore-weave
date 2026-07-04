"""loreweave_obs.logging_setup — the shared structured-logging installer (P2·A2a).

One ``setup_logging(service_name)`` call per Python service, replacing the three
copy-pasted ``app/logging_config.py`` (knowledge / composition / lore-enrichment)
and the plain ``basicConfig`` of the hot-path workers. Two things it unifies:

  * **One Redactor** — the SUPERSET of the three services' secret shapes (the
    ``sk-…`` / ``Bearer …`` pair plus lore-enrichment's generic ``api-key=…`` /
    ``token:…`` / ``secret=…`` / ``password:…`` catch-all). Defense-in-depth: a
    stray log of a request header or a provider error body never leaks a token.
  * **Dual trace id (the A1 correlation-id unification)** — every record carries
    BOTH ``trace_id`` (the bespoke per-request ``X-Trace-Id`` a 500 body echoes,
    for a human grepping logs) AND ``otel_trace_id`` (the W3C id Grafana Tempo
    indexes by, so Loki logs finally JOIN Tempo traces). The two were previously
    disjoint namespaces; stamping both on the line is the join key.

Per-service correlation ContextVars (e.g. lore-enrichment's ``job_id`` / ``stage``)
are passed via ``extra_context`` so the one installer covers the rich services
without the simple ones carrying dead fields.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar


def _json_formatter(fmt: str) -> logging.Formatter:
    """Build a python-json-logger JSON formatter.

    Imported LAZILY (only when ``setup_logging`` actually installs a handler) so
    that merely importing ``loreweave_obs`` — e.g. a worker that uses ONLY
    ``setup_tracing`` — never requires ``python-json-logger``. The tracing SDK's
    importability must not depend on a logging dependency (this decoupling is why
    the top-level import was removed; see /review-impl P2·A2a)."""
    try:  # newer python-json-logger
        from pythonjsonlogger.json import JsonFormatter  # type: ignore
    except ImportError:  # older python-json-logger
        from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore
    return JsonFormatter(fmt)

#: The canonical bespoke per-request trace id — ONE ContextVar fleet-wide. Each
#: service's ``TraceIdMiddleware`` imports and sets it; the ``ContextFilter`` and
#: the service HTTP clients read it. Empty outside a request scope.
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

#: Superset of the three services' secret shapes (lore-enrichment's was richest).
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*\S+"),
]
_REDACTED = "***REDACTED***"

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def new_trace_id() -> str:
    """A fresh 32-char hex request id (uuid4). Mirrors the Go/Python wire form."""
    return uuid.uuid4().hex


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
    """Stamp every record with the service name + BOTH trace ids + extras.

    ``otel_trace_id`` is read live from the active OTel span (lazy import keeps
    this module free of a hard opentelemetry dependency and sidesteps any import
    cycle with the package ``__init__``). Returns "" when no span is active or
    OTel is unconfigured — the log line still emits, just without a Tempo id.
    """

    def __init__(
        self,
        service_name: str,
        extra_context: dict[str, ContextVar] | None = None,
    ) -> None:
        super().__init__()
        self._service = service_name
        self._extra = dict(extra_context or {})

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        record.trace_id = trace_id_var.get() or ""
        try:  # lazy — avoids a hard OTel dep + the __init__ import cycle
            from loreweave_obs import current_otel_trace_id

            record.otel_trace_id = current_otel_trace_id()
        except Exception:
            record.otel_trace_id = ""
        for field, var in self._extra.items():
            setattr(record, field, var.get() or "")
        return True


def _build_handler(
    service_name: str, extra_context: dict[str, ContextVar] | None
) -> logging.Handler:
    handler = logging.StreamHandler()
    extra_fields = " ".join(f"%({field})s" for field in (extra_context or {}))
    fmt = (
        "%(asctime)s %(levelname)s %(name)s %(service)s "
        "%(trace_id)s %(otel_trace_id)s "
        + (extra_fields + " " if extra_fields else "")
        + "%(message)s"
    )
    handler.setFormatter(_json_formatter(fmt))
    handler.addFilter(ContextFilter(service_name, extra_context))
    handler.addFilter(RedactFilter())
    return handler


def setup_logging(
    service_name: str,
    *,
    level: str = "INFO",
    extra_context: dict[str, ContextVar] | None = None,
) -> None:
    """Install the shared JSON handler on root + uvicorn loggers (idempotent).

    ``service_name`` is stamped on every record. ``extra_context`` maps extra
    field names to ContextVars stamped per record (e.g.
    ``{"job_id": job_id_var, "stage": stage_var}`` for lore-enrichment). Safe to
    call more than once — it removes any handlers it (or uvicorn) previously
    installed before adding a fresh one.
    """
    level_upper = level.upper()

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(_build_handler(service_name, extra_context))
    root.setLevel(level_upper)

    # Uvicorn installs its own loggers with plain formatters; replace their
    # handlers so access/error logs flow through our JSON formatter too.
    for name in _UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(_build_handler(service_name, extra_context))
        lg.setLevel(level_upper)
        lg.propagate = False
