import logging

from app.logging_config import ContextFilter, RedactFilter, new_trace_id, trace_id_var


def _make_record(msg: str, *args) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_redact_filter_strips_api_key():
    f = RedactFilter()
    rec = _make_record("leaked sk-abcdefghijklmnopqrst1234567890")
    f.filter(rec)
    assert "sk-abcdefghijklmnopqrst" not in rec.msg
    assert "***REDACTED***" in rec.msg


def test_redact_filter_strips_bearer():
    f = RedactFilter()
    rec = _make_record("auth: Bearer abc.def.ghi")
    f.filter(rec)
    assert "abc.def.ghi" not in rec.msg


def test_context_filter_injects_trace_id():
    f = ContextFilter()
    tok = trace_id_var.set("trace-xyz")
    try:
        rec = _make_record("hello")
        f.filter(rec)
        assert rec.trace_id == "trace-xyz"
        assert rec.service == "knowledge-service"
    finally:
        trace_id_var.reset(tok)


def test_new_trace_id_is_unique():
    assert new_trace_id() != new_trace_id()
