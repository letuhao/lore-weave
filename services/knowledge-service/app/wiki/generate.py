"""Wiki generation — single-pass generate + rule-gate orchestration (M3 / §C4).

The core proof: turn a per-entity context (M2) + the book profile (M1) into a
grounded :class:`WikiArticleIR`. Flow per §C4:

    build_messages → LLM submit_and_wait("chat") → markdown → parse_article (M0)
                   → rule-gate (M3) → keep, or 1× corrective retry → result

Reuses the existing `LLMClient` (provider-registry `submit_and_wait`; retry +
metering free) — no clone. NEVER raises: an LLM error / non-completed job / empty
body / failed gate all resolve to a typed status so the (M6) orchestrator decides
fallback (the Go deterministic stub) or skip. The CanonVerifier + bounded revise
(M4) wrap THIS result; M3 stops at the deterministic rule-gate + one re-prompt.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from loreweave_extraction.reasoning_wire import reasoning_wire_fields

from app.clients.book_profile_client import BookProfile
from app.clients.llm_client import LLMClient
from app.wiki.context import GenerationContext
from app.wiki.ir import WikiArticleIR
from app.wiki.parse import parse_article
from app.wiki.prompt import build_messages
from app.wiki.rulegate import GateResult, evaluate

logger = logging.getLogger(__name__)

#: Generation outcome. `ok` = gated article ready; the rest are skip reasons the
#: orchestrator maps to "leave the deterministic stub" / "retry later".
GenerateStatus = Literal["ok", "skipped_no_grounding", "empty", "llm_failed"]

#: Output-token budget for one article. Generous (a long character article) but
#: bounded so a runaway generation can't burn unbounded tokens (risk #6). Partial
#: Markdown from a truncated response still parses (the parser is total).
DEFAULT_MAX_TOKENS = 4000

_RETRY_CORRECTIVE = (
    "Your previous draft made claims without citing the provided sources. Cite "
    "EVERY non-trivial claim inline with one of the provided [P]/[G]/[K] labels, "
    "and OMIT any claim you cannot support with a source."
)
_EMPTY_CORRECTIVE = (
    "Your previous response was empty or malformed. Produce the article now in "
    "the required constrained-Markdown format."
)


class GenerateResult(BaseModel):
    """The generation outcome. ``ir`` is the parsed article when ``status='ok'``
    (and the best/last IR on a soft failure, for diagnostics); ``gate`` carries
    the rule-gate counts; ``attempts`` is how many LLM calls ran."""

    status: GenerateStatus
    ir: WikiArticleIR | None = None
    gate: GateResult | None = None
    attempts: int = 0
    raw_markdown: str = ""
    # Carried through from the M2 context so a degraded generation (e.g. an
    # unindexed book → 0 passages, brief+KG only) is distinguishable downstream
    # from a fully-grounded one. Empty {} = no degradation.
    degraded: dict[str, str] = Field(default_factory=dict)


async def _call_llm(
    llm: LLMClient,
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    reasoning_effort: str = "none",
) -> str | None:
    """One generation LLM call → the Markdown body, or ``None`` on any failure
    (exception / non-completed job). A completed-but-contentless job → ``""``.

    D-KG-WIKI-WORKER-GRADED-EFFORT: the stored ``wiki_gen_jobs.reasoning_effort``
    (clamped at mint, W4) is applied to the prose-generation call — default
    "none" emits NO wire fields (byte-identical for the prior path)."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                # D-KG-WIKI-WORKER-GRADED-EFFORT — graded effort wire fields
                # ({} default ⇒ unchanged for non-opt-in callers).
                **reasoning_wire_fields(reasoning_effort),
            },
            job_meta={"feature": "wiki_generate"},
            transient_retry_budget=1,
        )
    except Exception as exc:  # noqa: BLE001 — generation must not crash on LLM error
        logger.warning("wiki generate LLM call failed: %s", exc)
        return None
    if getattr(job, "status", None) != "completed":
        logger.warning("wiki generate job status=%s", getattr(job, "status", None))
        return None
    payload = job.result or {}
    out = payload.get("messages") or []
    if isinstance(out, list) and out and isinstance(out[0], dict):
        return out[0].get("content", "") or ""
    return ""


async def generate_article(
    *,
    context: GenerationContext,
    profile: BookProfile,
    llm: LLMClient,
    user_id: str,
    model_source: str,
    model_ref: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.3,
    max_attempts: int = 2,
    initial_corrective: str | None = None,
    exemplars: list[tuple[str, str]] | None = None,
    # D-KG-WIKI-WORKER-GRADED-EFFORT — graded effort for the prose call
    # (default "none" ⇒ no wire fields, byte-identical for prior callers).
    reasoning_effort: str = "none",
) -> GenerateResult:
    """Generate one grounded article IR for ``context``'s entity (bounded retry).

    Returns ``status='ok'`` with the gated ``ir`` on success; otherwise a typed
    skip status (``skipped_no_grounding`` / ``empty`` / ``llm_failed``) with the
    last IR (if any) for diagnostics. Never raises. ``max_attempts`` caps the LLM
    calls (1 generate + up to N-1 corrective re-prompts). ``initial_corrective``
    seeds the FIRST prompt with a note (the M4 revise pass uses it to feed the
    verify flags back into a re-generation)."""
    brief = context.brief
    last = GenerateResult(status="llm_failed")
    corrective: str | None = initial_corrective

    for attempt in range(1, max_attempts + 1):
        messages = build_messages(
            brief=brief, profile=profile, items=context.items, corrective=corrective,
            exemplars=exemplars,
        )
        markdown = await _call_llm(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            messages=messages, max_tokens=max_tokens, temperature=temperature,
            reasoning_effort=reasoning_effort,
        )
        if markdown is None:
            last = GenerateResult(status="llm_failed", attempts=attempt)
            corrective = None  # a transport failure isn't the model's fault
            continue
        markdown = markdown.strip()
        if not markdown:
            last = GenerateResult(status="empty", attempts=attempt)
            corrective = _EMPTY_CORRECTIVE
            continue

        ir = parse_article(
            markdown,
            entity_id=brief.entity_id,
            display_name=brief.name,
            kind=brief.kind,
            language=profile.language,
            sources=context.sources,
        )
        gate = evaluate(ir)
        last = GenerateResult(
            status="skipped_no_grounding", ir=ir, gate=gate,
            attempts=attempt, raw_markdown=markdown,
        )
        if gate.passed:
            last.status = "ok"
            last.degraded = dict(context.degraded)
            return last
        corrective = _RETRY_CORRECTIVE  # ungrounded → nudge toward citing

    last.degraded = dict(context.degraded)
    return last
