"""knowledge-service logging shim wiring (P2·A2a).

The redaction / context-filter / JSON-format LOGIC now lives in loreweave_obs and
is exhaustively tested in sdks/python/tests/test_loreweave_obs_logging.py. This
suite only proves the service's thin adapter is wired correctly: it re-exports the
CANONICAL trace_id_var (so the middleware, the HTTP clients and the log filter all
share ONE var) and binds this service's name into the shared installer.
"""

import io
import json
import logging

import loreweave_obs
from app.logging_config import new_trace_id, setup_logging, trace_id_var


def test_trace_id_var_is_the_canonical_shared_var():
    # Same object as the SDK's — the middleware sets it, the clients + the log
    # filter read it. A separate copy here would silently break correlation.
    assert trace_id_var is loreweave_obs.trace_id_var


def test_new_trace_id_is_unique():
    assert new_trace_id() != new_trace_id()


def test_setup_logging_binds_service_name_and_trace_id():
    setup_logging("INFO")
    buf = io.StringIO()
    logging.getLogger().handlers[0].stream = buf
    tok = trace_id_var.set("trace-xyz")
    try:
        logging.getLogger("test").error("hello")
    finally:
        trace_id_var.reset(tok)
    rec = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert rec["service"] == "knowledge-service"
    assert rec["trace_id"] == "trace-xyz"
    assert "otel_trace_id" in rec  # dual-emit key always present
