"""Phase 4a-δ — extraction-pipeline error types.

Hoisted out of the deleted `llm_json_parser.py` so the 4 extractors and
their tests have a stable home for `ExtractionError` / `ExtractionStage`
after the K17.3 wrapper module retires.
"""

from __future__ import annotations

from typing import Literal

__all__ = ["ExtractionError", "ExtractionStage"]


ExtractionStage = Literal[
    "retry_parse",
    "retry_validate",
    "provider",
    "provider_exhausted",
    "cancelled",
]


class ExtractionError(Exception):
    """Terminal failure from an LLM extractor.

    `last_error` chains the underlying exception (LLMError subclass,
    JSONDecodeError, or ValidationError). `raw_content` carries the
    last LLM output (even if malformed) so K16 job failure rows can
    persist it for post-mortem debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: ExtractionStage,
        trace_id: str | None = None,
        last_error: Exception | None = None,
        raw_content: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.trace_id = trace_id
        self.last_error = last_error
        self.raw_content = raw_content
