"""P3 — LLM-powered level summarizer.

Spec: docs/specs/2026-05-23-p3-hierarchical-reduce.md §D7.

Generates a 2-3 sentence summary of a `chapter | part | book` level
for the hierarchical retrieval index. Inputs are bounded (joined child
texts truncated; entity names list) — no chunking needed at the
gateway layer.

Returns a single `LevelSummary` Pydantic; persistence is the caller's
responsibility (P3 summary_processor writes to summary_chapters /
summary_parts / summary_books + embeds into the per-level Neo4j vector
index).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from loreweave_extraction._types import LLMClientProtocol
from loreweave_extraction.errors import ExtractionError
from loreweave_extraction.prompts import load_prompt

logger = logging.getLogger(__name__)

__all__ = ["LevelSummary", "summarize_level"]


# L3 fix (spec D7): max_length=2000 at Pydantic; writer truncates to 500
# at persistence. Memory `feedback_llm_schema_tolerate_filter_dont_reject`.
class LevelSummary(BaseModel):
    summary_text: str = Field(min_length=20, max_length=2000)
    token_usage: dict[str, Any] = Field(default_factory=dict)


# Max chars of joined child text sent to LLM. Spec D7 says 8000 — keeps
# the prompt within a typical 4K-token context budget for the LLM call.
_MAX_CHILD_TEXT_CHARS = 8000

# Max entity names included in prompt to keep token budget bounded.
_MAX_ENTITY_NAMES = 30


async def summarize_level(
    *,
    level: Literal["chapter", "part", "book"],
    child_texts: list[str],
    entity_names: list[str],
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClientProtocol,
) -> LevelSummary:
    """Generate a 2-3 sentence summary of *level* via the BYOK LLM.

    Args:
        level: "chapter" | "part" | "book" — controls prompt phrasing.
        child_texts: text content from the children of this level
            (chapter -> joined scene leaf_texts; part -> chapter
            summaries; book -> part summaries). Truncated to
            _MAX_CHILD_TEXT_CHARS before sending.
        entity_names: top entities at this level (e.g. top-30 by
            mention frequency). Included in prompt for grounding.
        user_id, project_id, model_source, model_ref, llm_client:
            standard extraction kwargs (match the 4 existing extractors).

    Returns:
        LevelSummary with summary_text (20-2000 chars; writer
        truncates to 500 at persistence) and token_usage dict.

    Raises:
        ExtractionError: on terminal LLM / parse / validation failure.
        ValueError: if level is unknown or child_texts is empty.
    """
    if level not in ("chapter", "part", "book"):
        raise ValueError(f"unknown level {level!r}")
    if not child_texts:
        raise ValueError("child_texts must not be empty")

    joined = "\n\n".join(t.strip() for t in child_texts if t.strip())
    if not joined:
        raise ValueError("child_texts joined to empty string")
    if len(joined) > _MAX_CHILD_TEXT_CHARS:
        joined = joined[:_MAX_CHILD_TEXT_CHARS] + "\n[...truncated]"

    capped_entities = entity_names[:_MAX_ENTITY_NAMES]
    safe_entities = json.dumps(capped_entities, ensure_ascii=False).replace(
        "{", "{{"
    ).replace("}", "}}")

    prompt = load_prompt(
        "summarize_level",
        level=level,
        entity_names=safe_entities,
        child_texts=joined,
    )

    raw = await _call_llm(
        llm_client=llm_client,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        prompt=prompt,
    )
    return _postprocess(raw)


async def _call_llm(
    *,
    llm_client: LLMClientProtocol,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    prompt: str,
) -> dict[str, Any]:
    """Submit summarize_level job via the gateway; return raw response dict.

    Single-shot call (no chunking — input is bounded by _MAX_CHILD_TEXT_CHARS).
    Returns {"summary_text": ..., "token_usage": ...} from gateway.
    """
    try:
        # Match the existing extractors' submit pattern via LLMClientProtocol.
        # Knowledge-service LLMClient + tests both honor this contract.
        response = await llm_client.submit_and_wait(
            operation="summarize_level",
            user_id=user_id,
            project_id=project_id,
            model_source=model_source,
            model_ref=model_ref,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Generate the summary now."},
            ],
        )
    except Exception as exc:
        # Per LLMClientProtocol — re-raise as ExtractionError so caller can
        # branch on stage. summarize_level stage is "summarize".
        raise ExtractionError(
            stage="summarize",
            message=f"LLM call failed: {exc}",
        ) from exc

    # Gateway response shape: {"result": {"text": "...", "usage": {...}}} —
    # may differ by provider adapter; defensive read.
    result = response.get("result") or {}
    if not isinstance(result, dict):
        raise ExtractionError(
            stage="summarize",
            message=f"unexpected result shape: {type(result).__name__}",
        )
    return result


def _postprocess(raw: dict[str, Any]) -> LevelSummary:
    """Parse the LLM's JSON-line response into LevelSummary."""
    text_content = raw.get("text") or raw.get("content") or ""
    if not isinstance(text_content, str) or not text_content.strip():
        raise ExtractionError(
            stage="summarize",
            message=f"empty or non-string LLM response text: {text_content!r}",
        )
    # Strip code fences (memory `feedback_mock_only_coverage_hides_crossservice_bugs`
    # — gateway aggregator handles ```json fences but defensive at extractor too).
    stripped = text_content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ExtractionError(
            stage="summarize",
            message=f"LLM response not JSON: {exc}",
        ) from exc
    if not isinstance(parsed, dict) or "summary_text" not in parsed:
        raise ExtractionError(
            stage="summarize",
            message=f"LLM response missing summary_text: {parsed!r}",
        )
    try:
        return LevelSummary(
            summary_text=parsed["summary_text"],
            token_usage=raw.get("usage", {}),
        )
    except ValidationError as exc:
        raise ExtractionError(
            stage="summarize",
            message=f"LevelSummary validation failed: {exc.errors()}",
        ) from exc
