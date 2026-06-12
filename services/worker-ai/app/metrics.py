"""Cycle 73h — Prometheus metrics for worker-ai.

Worker-ai has no FastAPI HTTP surface (pure asyncio background worker).
This module ships a separate `prometheus_client.start_http_server` on
the configured METRICS_PORT (default 8094 internal, mapped to host
8226 in compose). The WSGI server runs in a daemon thread so it
doesn't interfere with the asyncio job-poll loop.

The single dedicated counter here is `worker_ai_filter_reload_total`
(cycle 73f r3 M4 fold; cycle 73g shipped log-only as a stopgap; this
cycle promotes to Prometheus-visible).

Pre-seeded outcomes: `applied` (subscriber successfully re-read Redis
and swapped module cache), `failed` (re-read raised an exception),
`startup` (hydrate succeeded), `startup_failed` (hydrate raised).

When METRICS_PORT is empty/zero, the server is NOT started — useful
for unit tests and dev environments that don't want the extra port.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from prometheus_client import CollectorRegistry, Counter, start_http_server

__all__ = [
    "registry",
    "worker_ai_filter_reload_total",
    "worker_ai_extraction_zero_output_total",
    "worker_ai_extraction_reasoning_model_advised_total",
    "start_metrics_server",
]

logger = logging.getLogger(__name__)

# Dedicated registry — mirrors knowledge-service pattern. Lets future
# tests build a fresh registry without polluting prometheus's GLOBAL
# default. Counter is also registered against this registry.
registry = CollectorRegistry()

# Cycle 73f r3 M4 fold → cycle 73h fold: replace log-only emission
# with Prometheus counter. Outcome cardinality is closed at 4:
#   - applied         : subscriber re-read Redis + swapped cache OK
#   - failed          : subscriber tried re-read + caught exception
#   - startup         : startup hydrate fired (Redis had a key)
#   - startup_failed  : startup hydrate raised (Redis unreachable etc.)
# Total series: 4.
worker_ai_filter_reload_total = Counter(
    "worker_ai_filter_reload_total",
    "Cycle 73h — worker-ai Pass2 precision filter reload outcomes. "
    "`applied`/`failed` track pubsub-driven re-reads; `startup`/"
    "`startup_failed` track lifespan hydrate. Greppable log token "
    "`WORKER_FILTER_RELOAD` mirrors each outcome for legacy ops "
    "tooling that doesn't scrape Prometheus.",
    ["outcome"],
    registry=registry,
)
for _out in ("applied", "failed", "startup", "startup_failed"):
    worker_ai_filter_reload_total.labels(outcome=_out)

# FD-27 — silent zero-output extraction guard. Fires when an extraction item
# had non-empty input text but the LLM produced NOTHING (0 entities + relations
# + events + facts). The dominant cause is a reasoning model whose JSON output
# is swallowed by reasoning tokens (qwen3.x-thinking, deepseek-r1) when thinking
# isn't disabled — but it's cause-agnostic (also catches a bad prompt / model
# misconfig). Greppable log token `EXTRACTION_ZERO_OUTPUT`. `source_type`
# cardinality is closed at the extraction source kinds (chapter/chat_message).
worker_ai_extraction_zero_output_total = Counter(
    "worker_ai_extraction_zero_output_total",
    "FD-27 — extraction items that yielded zero candidates on non-empty input "
    "(silent 'extraction did nothing'). Log token `EXTRACTION_ZERO_OUTPUT`.",
    ["source_type"],
    registry=registry,
)

# FD-27 — reasoning-model advisory. Fires once per job when the configured
# extraction model's name matches a reasoning-model heuristic (best-effort,
# name-based — see `_is_likely_reasoning_model`). Recommends reasoning_effort=
# none / enable_thinking=false. Greppable log token `EXTRACTION_REASONING_MODEL`.
worker_ai_extraction_reasoning_model_advised_total = Counter(
    "worker_ai_extraction_reasoning_model_advised_total",
    "FD-27 — extraction jobs whose configured model looks like a reasoning "
    "model (advisory; recommend disabling thinking). Log token "
    "`EXTRACTION_REASONING_MODEL`.",
    registry=registry,
)


_server_thread: Optional[threading.Thread] = None


def start_metrics_server(port: int) -> None:
    """Start the prometheus_client WSGI server on `port` in a daemon
    thread. Idempotent: calling twice is a no-op (the first server
    keeps running).

    When `port` is 0 (or negative), the server is NOT started — caller
    receives a debug log and the function returns. Useful for tests
    and dev runs.

    Daemon thread means the server is killed when the asyncio main
    loop exits (no clean shutdown needed; Prometheus scrape interval
    handles missing scrapes gracefully).
    """
    global _server_thread
    if _server_thread is not None and _server_thread.is_alive():
        logger.debug("metrics server already running (no-op)")
        return
    if port is None or port <= 0:
        logger.info("metrics server disabled (port=%s)", port)
        return
    # start_http_server returns None in older prometheus_client; in newer
    # versions returns (server, thread). Either way the daemon thread it
    # spawns serves /metrics on 0.0.0.0:port until process exit.
    result = start_http_server(port, registry=registry)
    if isinstance(result, tuple) and len(result) == 2:
        _, _server_thread = result
    else:
        # Older API — server thread not exposed; create sentinel to
        # avoid double-start on idempotent re-call.
        _server_thread = threading.current_thread()
    logger.info(
        "cycle 73h: worker-ai metrics server listening on :%d/metrics", port,
    )
