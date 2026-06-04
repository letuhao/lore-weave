import logging
import re
import uuid
from contextvars import ContextVar

try:
    from pythonjsonlogger.json import JsonFormatter  # type: ignore
except ImportError:  # older python-json-logger
    from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
]
_REDACTED = "***REDACTED***"

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(_REDACTED, text)
    return text


class RedactFilter(logging.Filter):
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
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get() or ""
        record.service = "knowledge-service"
        return True


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _build_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(service)s %(trace_id)s %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())
    handler.addFilter(RedactFilter())
    return handler


def setup_logging(level: str = "INFO") -> None:
    level_upper = level.upper()

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(_build_handler())
    root.setLevel(level_upper)

    # Uvicorn installs its own loggers with propagate=False and plain formatters.
    # Replace their handlers and enable propagation so they flow through our root.
    for name in _UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(_build_handler())
        lg.setLevel(level_upper)
        lg.propagate = False
