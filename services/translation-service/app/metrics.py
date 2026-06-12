"""Translation-pipeline instrumentation (M0 / W10).

A dependency-free structured-event emitter so per-chapter and per-batch latency,
token, retry, and outcome data are observable in logs — greppable on the
``translation.metric`` marker. A real metrics backend (e.g. Prometheus) can later
subscribe by replacing ``record_stage``'s body; the call sites stay identical.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger("translation.metrics")


def _fmt(v: Any) -> str:
    return f"{v:.3f}" if isinstance(v, float) else str(v)


def record_stage(stage: str, **fields: Any) -> None:
    """Emit one structured stage event as a single greppable log line.

    Never raises — instrumentation must not break the translation pipeline. A
    metric failure AFTER a chapter's successful persist would otherwise propagate
    up, get the chapter marked FAILED, and corrupt the job counters.
    """
    try:
        parts = " ".join(f"{k}={_fmt(v)}" for k, v in fields.items())
        log.info("translation.metric stage=%s %s", stage, parts)
    except Exception:  # pragma: no cover - instrumentation must never break callers
        pass


@contextmanager
def timed(stage: str, **fields: Any) -> Iterator[dict]:
    """Time a block and emit ``stage`` with ``duration_s`` + ``outcome``.

    The caller may set ``ctx['outcome']`` on the yielded dict; it defaults to
    ``'ok'``, or ``'error'`` if the block raises (the exception still propagates).
    """
    ctx: dict[str, Any] = {"outcome": "ok"}
    start = time.monotonic()
    try:
        yield ctx
    except Exception:
        ctx["outcome"] = "error"
        raise
    finally:
        record_stage(stage, duration_s=time.monotonic() - start, outcome=ctx["outcome"], **fields)
