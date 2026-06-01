"""PersistenceAdapter seam — where a scored EvalResult is written.

The scorer (``score_dump``) is decoupled from storage via the ``EvalSink``
Protocol. The SDK ships ``FileSink`` (writes JSON to disk — the current R&D
behavior). Track phase Q1 adds a ``DbSink`` IN learning-service (NOT here — the
SDK must not know the learning-service schema) that implements the same Protocol
and writes the ``eval_runs`` / ``eval_results`` / ``quality_scores`` rows.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .scorer import EvalResult


@runtime_checkable
class EvalSink(Protocol):
    """Persist a scored EvalResult. Async because the production sink
    (``DbSink`` in learning-service, phase Q1) does DB I/O; ``FileSink`` is
    async too so every caller awaits the same contract."""

    async def write_eval_result(self, result: EvalResult) -> Any: ...


class FileSink:
    """Write the EvalResult as JSON to ``<out_dir>/eval_result.json`` — the
    R&D-parity sink (keeps the structured result next to the dump). Returns the
    written path. ``async`` to match the EvalSink contract (the file write
    itself is synchronous).
    """

    def __init__(self, out_dir: Path) -> None:
        self._out = Path(out_dir)

    async def write_eval_result(self, result: EvalResult) -> Path:
        self._out.mkdir(parents=True, exist_ok=True)
        path = self._out / "eval_result.json"
        path.write_text(
            json.dumps(asdict(result), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path
