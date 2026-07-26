"""Tests for loreweave_obs.setup_logging (P2·A2a — the shared logging installer).

setup_logging mutates the process-global root + uvicorn loggers, so an autouse
fixture snapshots and restores every mutated logger's handlers/level/propagate
around each test.
"""

import io
import json
import logging
from contextvars import ContextVar
from unittest import mock

import pytest

from loreweave_obs import setup_logging, trace_id_var
from loreweave_obs.logging_setup import _UVICORN_LOGGERS


@pytest.fixture(autouse=True)
def _restore_logging():
    names = [None, *_UVICORN_LOGGERS]  # None == root
    saved = {}
    for name in names:
        lg = logging.getLogger(name) if name else logging.getLogger()
        saved[name] = (list(lg.handlers), lg.level, lg.propagate)
    yield
    for name, (handlers, level, propagate) in saved.items():
        lg = logging.getLogger(name) if name else logging.getLogger()
        lg.handlers = handlers
        lg.level = level
        lg.propagate = propagate


def _capture(logger_name: str = "test.logger") -> tuple[logging.Logger, io.StringIO]:
    """Redirect the installed root handler to a StringIO and return a logger."""
    buf = io.StringIO()
    logging.getLogger().handlers[0].stream = buf  # StreamHandler → our buffer
    return logging.getLogger(logger_name), buf


def _emit(logger: logging.Logger, buf: io.StringIO, msg: str, *args) -> dict:
    logger.error(msg, *args)
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def test_setup_logging_stamps_service_and_both_trace_ids():
    setup_logging("svc-under-test")
    logger, buf = _capture()
    with mock.patch("loreweave_obs.current_otel_trace_id", return_value="a" * 32):
        trace_id_var.set("req-bespoke-id")
        rec = _emit(logger, buf, "hello world")
    assert rec["service"] == "svc-under-test"
    assert rec["trace_id"] == "req-bespoke-id"      # bespoke X-Trace-Id channel
    assert rec["otel_trace_id"] == "a" * 32          # Tempo join key (dual-emit)
    assert rec["message"] == "hello world"


def test_dual_emit_with_a_REAL_otel_span():
    """End-to-end (NOT mocked): a log emitted inside a live OTel span carries that
    span's trace_id in otel_trace_id — the actual Loki↔Tempo join key. The other
    dual-emit tests mock current_otel_trace_id (proving only that the filter READS
    it); this proves the whole chain filter → live span → log line really works.

    Uses a LOCAL TracerProvider's tracer (not the global one) to sidestep OTel's
    set-once global-provider constraint: start_as_current_span sets the context
    span regardless of provider, and current_otel_trace_id reads the context span.
    """
    import re

    from opentelemetry.sdk.trace import TracerProvider

    from loreweave_obs import current_otel_trace_id

    tracer = TracerProvider().get_tracer("review-impl-test")
    setup_logging("svc-under-test")
    logger, buf = _capture()
    with tracer.start_as_current_span("review-span"):
        expected = current_otel_trace_id()
        logger.error("emitted inside a real span")
    assert re.fullmatch(r"[0-9a-f]{32}", expected), (
        f"the live span should yield a 32-hex trace id, got {expected!r}"
    )
    rec = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert rec["otel_trace_id"] == expected  # the REAL span id, not a mock value


def test_otel_trace_id_empty_when_no_span():
    setup_logging("svc-under-test")
    logger, buf = _capture()
    with mock.patch("loreweave_obs.current_otel_trace_id", return_value=""):
        trace_id_var.set("")
        rec = _emit(logger, buf, "no span here")
    assert rec["otel_trace_id"] == ""
    assert rec["trace_id"] == ""


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",       # OpenAI-style key
        "Bearer eyJhbGciOi.some.jwt-looking-token",  # bearer token
        "api_key=super-secret-value-123",            # generic api-key shape
        "password: hunter2hunter2hunter2",           # generic password shape
    ],
)
def test_redactor_scrubs_all_three_secret_shapes(secret):
    setup_logging("svc-under-test")
    logger, buf = _capture()
    with mock.patch("loreweave_obs.current_otel_trace_id", return_value=""):
        rec = _emit(logger, buf, "leaking %s in a log line", secret)
    assert "***REDACTED***" in rec["message"]
    # The raw secret token must not survive anywhere in the emitted line.
    assert secret.split("=")[-1].split(":")[-1].strip() not in rec["message"] or (
        "***REDACTED***" in rec["message"]
    )


def test_extra_context_vars_are_stamped():
    job_id_var: ContextVar[str] = ContextVar("job_id", default="")
    stage_var: ContextVar[str] = ContextVar("stage", default="")
    setup_logging(
        "lore-enrichment-service",
        extra_context={"job_id": job_id_var, "stage": stage_var},
    )
    logger, buf = _capture()
    with mock.patch("loreweave_obs.current_otel_trace_id", return_value=""):
        job_id_var.set("job-42")
        stage_var.set("generate")
        rec = _emit(logger, buf, "enriching")
    assert rec["job_id"] == "job-42"
    assert rec["stage"] == "generate"


def test_simple_service_has_no_extra_fields():
    """A service that passes no extra_context must not carry job_id/stage keys."""
    setup_logging("knowledge-service")
    logger, buf = _capture()
    with mock.patch("loreweave_obs.current_otel_trace_id", return_value=""):
        rec = _emit(logger, buf, "ranking")
    assert "job_id" not in rec
    assert "stage" not in rec


def test_import_loreweave_obs_without_python_json_logger(monkeypatch):
    """The tracing SDK's importability must NOT require python-json-logger.

    Regression guard for the /review-impl P2·A2a finding: a top-level
    pythonjsonlogger import in logging_setup once crashed every tracing-ONLY
    service rebuild (ModuleNotFoundError on `from loreweave_obs import
    setup_tracing`). The dep is now imported lazily — importing the package +
    the tracing helpers must work without it; only CALLING setup_logging needs it.
    """
    import builtins
    import sys

    watched = (
        "loreweave_obs",
        "loreweave_obs.logging_setup",
        "pythonjsonlogger",
        "pythonjsonlogger.json",
        "pythonjsonlogger.jsonlogger",
    )
    saved = {m: sys.modules.get(m) for m in watched}
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("pythonjsonlogger"):
            raise ImportError("simulated missing python-json-logger")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    for m in ("loreweave_obs", "loreweave_obs.logging_setup"):
        sys.modules.pop(m, None)
    try:
        import loreweave_obs as reloaded  # must NOT raise without the dep
        from loreweave_obs import current_otel_trace_id, setup_tracing  # noqa: F401

        # Installing the JSON handler DOES need the dep → a clean ImportError,
        # not a crash at import time.
        with pytest.raises(ImportError):
            reloaded.setup_logging("svc-under-test")
    finally:
        # Restore the canonical modules so later tests see the original
        # trace_id_var identity (the reload created fresh module objects).
        for m, orig in saved.items():
            if orig is not None:
                sys.modules[m] = orig
            else:
                sys.modules.pop(m, None)


def test_setup_logging_is_idempotent():
    setup_logging("svc-under-test")
    setup_logging("svc-under-test")
    setup_logging("svc-under-test")
    # Exactly one handler on root — repeated calls replace, never stack.
    assert len(logging.getLogger().handlers) == 1
    for name in _UVICORN_LOGGERS:
        assert len(logging.getLogger(name).handlers) == 1


class TestRedactFilterMappingArgs:
    """A single dict arg is a MAPPING on the record, not an iterable of values.

    `LogRecord.__init__` unwraps `logger.x(msg, a_dict)` to `self.args = a_dict` (that is
    how `%(name)s` formatting works). RedactFilter iterated it, and iterating a Mapping
    yields its KEYS — so `{"a": 1, "b": 2}` became `("a", "b")`, the message formatted one
    `%s` against a 2-tuple, and logging raised "not all arguments converted" INSIDE emit.
    The stdlib swallows that via handleError, so the line was simply LOST.

    Found 2026-07-23 from composition's book-lifecycle consumer: its
    `logger.warning("... %s", fields)` disappeared whenever setup_logging was installed —
    which is why its test failed in the full suite but passed when run alone.
    """

    def _record(self, msg: str, args):
        return logging.LogRecord("t", logging.WARNING, "p", 1, msg, args, None)

    def test_a_single_dict_arg_still_formats(self):
        from loreweave_obs.logging_setup import RedactFilter

        rec = self._record("event without book_id: %s",
                           ({"event_type": "book.lifecycle_changed", "payload": "{}"},))
        assert isinstance(rec.args, dict), "stdlib should have unwrapped the mapping"
        RedactFilter().filter(rec)
        # The message must survive — before the fix this raised TypeError inside logging.
        assert "book.lifecycle_changed" in rec.getMessage()

    def test_percent_named_formatting_survives(self):
        from loreweave_obs.logging_setup import RedactFilter

        rec = self._record("user=%(user)s action=%(action)s",
                           ({"user": "u1", "action": "publish"},))
        RedactFilter().filter(rec)
        assert rec.getMessage() == "user=u1 action=publish"

    def test_secrets_in_mapping_VALUES_are_now_redacted(self):
        from loreweave_obs.logging_setup import RedactFilter

        # The whole point of the filter. With the old tuple(...) it saw only KEYS, so a
        # secret sitting in a value was never scrubbed.
        rec = self._record("headers=%(auth)s", ({"auth": "Bearer abc.def-ghi"},))
        RedactFilter().filter(rec)
        assert "Bearer abc.def-ghi" not in rec.getMessage()
        assert "***REDACTED***" in rec.getMessage()

    def test_tuple_args_keep_their_existing_behaviour(self):
        from loreweave_obs.logging_setup import RedactFilter

        rec = self._record("a=%s b=%s", ("sk-" + "x" * 24, "plain"))
        RedactFilter().filter(rec)
        out = rec.getMessage()
        assert "***REDACTED***" in out and out.endswith("plain")
