"""lore-enrichment-service logging shim wiring (P2·A2a).

The redaction / context-filter / JSON-format LOGIC now lives in loreweave_obs and
is exhaustively tested in sdks/python/tests/test_loreweave_obs_logging.py. This
suite only proves the service's thin adapter is wired correctly: it re-exports the
CANONICAL trace_id_var (so the middleware, the grant client and the log filter all
share ONE var), binds this service's name into the shared installer, and — the
RICH case for this service — passes its job_id / stage correlation ContextVars via
extra_context so they land on every emitted record.
"""

import io
import json
import logging

import loreweave_obs
from app.logging_config import (
    job_id_var,
    new_trace_id,
    setup_logging,
    stage_var,
    trace_id_var,
)


def test_trace_id_var_is_the_canonical_shared_var():
    # Same object as the SDK's — the middleware sets it, the clients + the log
    # filter read it. A separate copy here would silently break correlation.
    assert trace_id_var is loreweave_obs.trace_id_var


def test_job_id_and_stage_vars_are_service_owned():
    # These are lore-enrichment-specific — the shared installer does NOT define
    # them, so this service owns them locally and hands them to extra_context.
    assert not hasattr(loreweave_obs, "job_id_var")
    assert not hasattr(loreweave_obs, "stage_var")


def test_new_trace_id_is_unique():
    assert new_trace_id() != new_trace_id()


def test_setup_logging_binds_service_name_and_correlation_ids():
    setup_logging("INFO")
    buf = io.StringIO()
    logging.getLogger().handlers[0].stream = buf
    tok_t = trace_id_var.set("trace-xyz")
    tok_j = job_id_var.set("job-123")
    tok_s = stage_var.set("generate")
    try:
        logging.getLogger("test").error("hello")
    finally:
        stage_var.reset(tok_s)
        job_id_var.reset(tok_j)
        trace_id_var.reset(tok_t)
    rec = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert rec["service"] == "lore-enrichment-service"
    assert rec["trace_id"] == "trace-xyz"
    assert rec["job_id"] == "job-123"  # extra_context stamped
    assert rec["stage"] == "generate"  # extra_context stamped
    assert "otel_trace_id" in rec  # dual-emit key always present
