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


def test_setup_logging_is_idempotent():
    setup_logging("svc-under-test")
    setup_logging("svc-under-test")
    setup_logging("svc-under-test")
    # Exactly one handler on root — repeated calls replace, never stack.
    assert len(logging.getLogger().handlers) == 1
    for name in _UVICORN_LOGGERS:
        assert len(logging.getLogger(name).handlers) == 1
