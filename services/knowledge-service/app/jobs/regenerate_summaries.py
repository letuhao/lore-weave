"""K20.1 + K20.2 — L0 / L1 summary regeneration with drift prevention.

KSA §7.6 reference impl + drift rules:

1. Regeneration reads **raw source passages** (chat turns for L0; chat
   turns + chapters for L1), NOT the current summary. Prevents
   recursive amplification.
2. **User edit wins for 30 days.** If the user manually edited the
   summary within the last 30 days (`knowledge_summary_versions`
   row with `edit_source='manual'`), regen skips and returns
   ``status='user_edit_lock'``. No LLM call.
3. **Diversity check.** Compute Jaccard similarity between the LLM
   output and the current summary; skip if >0.95.
4. **Minimal guardrails** (K20.6 MVP): empty-output reject, token
   overflow reject, K15.6 injection-marker detection → reject.
5. **Race guard.** Read the current summary's `version` at step-start;
   pass it as `expected_version` on upsert. A concurrent manual edit
   bumps the version and we surface ``regen_concurrent_edit`` rather
   than silently clobber.

What this module does **not** do (deferred to later cycles):

- Scheduled auto-regen (K20.3).
- `/metrics` counters (K20.7).
- Cost tracking via `_record_spending` (D-K20α-01).
- Full K20.6 guardrails (2-failure retry, past-version dup check,
  markdown-artifact strip).

Callers: `app/api/internal/summarize.py` (service-to-service + future
K20.3 scheduler) and the public-edge handlers in
`app/routers/public/summaries.py`.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from app.clients.provider_client import ChatCompletionResponse, ProviderClient
from app.context.formatters.token_counter import estimate_tokens
from app.db.models import Summary
from app.db.neo4j_helpers import CypherSession, run_read
from app.db.repositories import VersionMismatchError
from app.db.repositories.summaries import SummariesRepo
from app.extraction.injection_defense import neutralize_injection
from app.metrics import (
    summary_regen_cost_usd_total,
    summary_regen_duration_seconds,
    summary_regen_tokens_total,
    summary_regen_total,
)
from app.pricing import cost_per_token

logger = logging.getLogger(__name__)

__all__ = [
    "RegenerationResult",
    "RegenerationStatus",
    "RegenTrigger",
    "regenerate_global_summary",
    "regenerate_project_summary",
]


# C2 — distinguishes human-initiated regens (public edge) from the
# K20.3 scheduler loop so operators can alert on "scheduler silent"
# or "manual regen spike" independently.
RegenTrigger = Literal["manual", "scheduled"]


# ── Tunables (KSA §7.6 reference values) ─────────────────────────────

_RECENT_PASSAGE_LIMIT = 50
_MAX_OUTPUT_TOKENS = 500
_SIMILARITY_NO_OP_THRESHOLD = 0.95
_USER_EDIT_LOCK_DAYS = 30

# K20.6 past-version dup check: consult the last N archived versions
# from `knowledge_summary_versions`. A match above the similarity
# threshold against any of them means the LLM regenerated content
# that's already been written-and-archived, so accepting would be
# churn without drift. 20 is deliberately small — history list panels
# show max 50 rows and a user experimenting with different prompts
# typically produces <10 distinct versions; beyond that the dup check
# is effectively a no-op either way.
_PAST_VERSION_DUP_CHECK_LIMIT = 20

# System prompts kept as module-level constants so tests can introspect
# them; KSA §7.6 explicitly forbids referring to the *current* summary
# content in the prompt — only raw passages inform the LLM.

_L0_SYSTEM_PROMPT = (
    "You are writing a short global bio describing the user's identity "
    "and writing preferences for use as AI context across all their "
    "projects. Focus on stable traits (language, genre affinity, prose "
    "style, factual interests). Do not infer a preference unless you "
    "see it stated at least 3 times in the source material. Output "
    "plain text only — no JSON, no markdown, no headings. Maximum 500 "
    "tokens."
)

_L1_SYSTEM_PROMPT = (
    "You are writing a short project summary for use as AI context. "
    "Focus on what's established, active, and unresolved in the "
    "project. Do not infer user preferences — describe the project "
    "itself. Output plain text only — no JSON, no markdown, no "
    "headings. Maximum 500 tokens."
)


# ── Public types ──────────────────────────────────────────────────────

RegenerationStatus = Literal[
    "regenerated",
    "no_op_similarity",
    "no_op_empty_source",
    "no_op_guardrail",
    "user_edit_lock",
    "regen_concurrent_edit",
]


class RegenerationResult(BaseModel):
    """Outcome of a single regen call.

    ``summary`` is populated only when ``status='regenerated'`` — for
    every no-op / skip status the existing summary is unchanged.
    ``skipped_reason`` is a short human-readable explanation, intended
    for the FE to surface directly in the Regenerate dialog.
    """

    status: RegenerationStatus
    summary: Summary | None = None
    skipped_reason: str | None = None


# ── Internal helpers ──────────────────────────────────────────────────

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _jaccard_similarity(a: str, b: str) -> float:
    """Normalized word-set Jaccard similarity in [0, 1].

    Both inputs are lowercased and tokenized on `\\w+` so case and
    punctuation don't affect the score. Two empty strings score 1.0
    (degenerate "identical"); one-empty-one-nonempty scores 0.0.
    """
    tokens_a = set(_WORD_RE.findall(a.lower()))
    tokens_b = set(_WORD_RE.findall(b.lower()))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


async def _has_recent_manual_edit(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    scope_type: Literal["global", "project"],
    scope_id: UUID | None,
    days: int = _USER_EDIT_LOCK_DAYS,
) -> bool:
    """Check `knowledge_summary_versions` for a manual edit in the
    last ``days``. KSA §7.6 rule 2 — user edits protected from auto /
    manual-regen for 30 days."""
    query = """
    SELECT 1
    FROM knowledge_summary_versions v
    JOIN knowledge_summaries s USING (summary_id)
    WHERE s.user_id = $1
      AND s.scope_type = $2
      AND s.scope_id IS NOT DISTINCT FROM $3
      AND v.user_id = $1
      AND v.edit_source = 'manual'
      AND v.created_at > now() - make_interval(days => $4)
    LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, user_id, scope_type, scope_id, days)
    return row is not None


async def _fetch_recent_passages(
    session: CypherSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    source_types: list[str],
    limit: int = _RECENT_PASSAGE_LIMIT,
) -> list[str]:
    """Fetch raw passage text, newest-first, for regen prompt input.

    When ``project_id`` is None: filter to `p.project_id IS NULL`
    (global-scope passages only). When set: filter to the given
    project_id. KSA §7.6 rule 5 — L0 vs L1 must not cross-contaminate.
    """
    if not source_types:
        return []
    if project_id is None:
        cypher = """
        MATCH (p:Passage)
        WHERE p.user_id = $user_id
          AND p.project_id IS NULL
          AND p.source_type IN $source_types
        RETURN p.text AS text
        ORDER BY p.created_at DESC
        LIMIT $limit
        """
        result = await run_read(
            session,
            cypher,
            user_id=str(user_id),
            source_types=source_types,
            limit=limit,
        )
    else:
        cypher = """
        MATCH (p:Passage)
        WHERE p.user_id = $user_id
          AND p.project_id = $project_id
          AND p.source_type IN $source_types
        RETURN p.text AS text
        ORDER BY p.created_at DESC
        LIMIT $limit
        """
        result = await run_read(
            session,
            cypher,
            user_id=str(user_id),
            project_id=str(project_id),
            source_types=source_types,
            limit=limit,
        )
    return [record["text"] async for record in result if record.get("text")]


def _build_messages(
    *,
    scope: Literal["global", "project"],
    passages: list[str],
) -> list[dict[str, Any]]:
    """Assemble the chat-completion messages for the regen call.

    Passages are joined with blank-line separators and labelled with a
    1-based index so the LLM can reference them if prompted to. Order
    is newest-first (matches `_fetch_recent_passages`), which biases
    recent context — still KSA-compliant since every passage is raw
    source, not a derived summary.
    """
    system_prompt = _L0_SYSTEM_PROMPT if scope == "global" else _L1_SYSTEM_PROMPT
    numbered = "\n\n".join(
        f"[{i + 1}] {text}" for i, text in enumerate(passages)
    )
    user_content = (
        f"Raw source passages (newest first):\n\n{numbered}\n\n"
        "Write the summary now."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _compute_llm_cost_usd(
    response: ChatCompletionResponse, model_ref: str
) -> Decimal:
    """Decimal USD cost from the provider's usage report × pricing.py
    rate. Returns ``Decimal("0")`` for self-hosted / unknown models
    (the fallback rate in ``pricing.py`` is conservative, not zero;
    we don't want to record a "$0 cost" that's actually a small real
    cost — better to use the fallback rate so dashboards at least
    approximate). The prompt+completion split is preserved so the
    two-label token counter can be incremented separately.
    """
    total_tokens = int(response.usage.total_tokens or 0)
    if total_tokens <= 0:
        return Decimal("0")
    return Decimal(total_tokens) * cost_per_token(model_ref)


def _guardrail_reject_reason(text: str) -> str | None:
    """Return a short rejection reason if ``text`` fails a K20.6 MVP
    guardrail, else None.

    Checks (in order):
      1. Empty / whitespace-only.
      2. Token count > `_MAX_OUTPUT_TOKENS`.
      3. K15.6 injection pattern present.
    """
    stripped = text.strip()
    if not stripped:
        return "empty_output"
    if estimate_tokens(stripped) > _MAX_OUTPUT_TOKENS:
        return "token_overflow"
    _, hit_count = neutralize_injection(stripped)
    if hit_count > 0:
        return "injection_detected"
    return None


# ── Core regen entrypoints ────────────────────────────────────────────

@dataclass
class _RegenContext:
    """Bundle of runtime deps. Passed explicitly so tests can swap any
    piece without monkey-patching modules."""

    pool: asyncpg.Pool
    session_factory: Any  # called as `session_factory()` → async CM
    provider_client: ProviderClient
    summaries_repo: SummariesRepo


async def _owns_project(pool: asyncpg.Pool, user_id: UUID, project_id: UUID) -> bool:
    """Cheap pre-flight ownership gate. The upsert CTE enforces the
    same check atomically at write time (see `upsert_project_scoped`),
    but that happens AFTER the LLM call — so a cross-user
    ``project_id`` would burn BYOK tokens before failing. This check
    prevents that waste. Review-impl M1.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM knowledge_projects WHERE user_id = $1 AND project_id = $2",
            user_id, project_id,
        )
    return row is not None


async def _regenerate_core(
    ctx: _RegenContext,
    *,
    user_id: UUID,
    scope_type: Literal["global", "project"],
    scope_id: UUID | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    source_types: list[str],
    trigger: RegenTrigger = "manual",
) -> RegenerationResult:
    """Shared regen flow for both L0 and L1.

    K20.7 + C2 instrumentation: every return path increments
    ``summary_regen_total{scope_type, status, trigger}``, and the
    wall-time histogram ``summary_regen_duration_seconds{scope_type}``
    covers the whole flow regardless of status. Successful regens
    also increment token-count and USD-cost counters using the LLM
    usage report + ``pricing.cost_per_token``. Duration/cost/tokens
    are NOT split by trigger — per-scope granularity is enough for
    capacity planning and splitting further would quadruple series
    count without matching operator need.
    """
    started_at = time.perf_counter()
    result = await _regenerate_core_inner(
        ctx,
        user_id=user_id,
        scope_type=scope_type,
        scope_id=scope_id,
        model_source=model_source,
        model_ref=model_ref,
        source_types=source_types,
    )
    summary_regen_total.labels(
        scope_type=scope_type, status=result.status, trigger=trigger
    ).inc()
    summary_regen_duration_seconds.labels(scope_type=scope_type).observe(
        time.perf_counter() - started_at
    )
    return result


async def _regenerate_core_inner(
    ctx: _RegenContext,
    *,
    user_id: UUID,
    scope_type: Literal["global", "project"],
    scope_id: UUID | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    source_types: list[str],
) -> RegenerationResult:
    """Inner flow. Split out from `_regenerate_core` so the metrics
    wrapper can see every return path (including mid-flow
    short-circuits) without repeating `summary_regen_total.inc()`
    at every `return RegenerationResult(...)` site.
    """

    # 0. Ownership pre-flight (project scope only). Review-impl M1:
    #    stop cross-user project_ids before they spend BYOK tokens.
    if scope_type == "project":
        assert scope_id is not None
        if not await _owns_project(ctx.pool, user_id, scope_id):
            return RegenerationResult(
                status="no_op_guardrail",
                skipped_reason=(
                    "Project not found or not owned by the calling user."
                ),
            )

    # 1. User edit lock — cheapest check first, skip LLM entirely on hit.
    if await _has_recent_manual_edit(
        ctx.pool, user_id=user_id, scope_type=scope_type, scope_id=scope_id,
    ):
        return RegenerationResult(
            status="user_edit_lock",
            skipped_reason=(
                f"A manual edit within the last {_USER_EDIT_LOCK_DAYS} days is "
                "protected from automatic regeneration."
            ),
        )

    # 2. Read current summary state — supplies expected_version for the
    #    race guard and the baseline content for the similarity check.
    current = await ctx.summaries_repo.get(user_id, scope_type, scope_id)
    expected_version = current.version if current is not None else None

    # 3. Fetch raw passages (KSA §7.6 rule 1 — never the current summary).
    project_id = scope_id if scope_type == "project" else None
    async with ctx.session_factory() as session:
        passages = await _fetch_recent_passages(
            session,
            user_id=user_id,
            project_id=project_id,
            source_types=source_types,
        )

    if not passages:
        return RegenerationResult(
            status="no_op_empty_source",
            skipped_reason=(
                "No recent source material (chat turns / chapters) is "
                "available to build a summary from. Write some content "
                "first, then try again."
            ),
        )

    # 4. LLM call via BYOK proxy.
    messages = _build_messages(scope=scope_type, passages=passages)
    response = await ctx.provider_client.chat_completion(
        user_id=str(user_id),
        model_source=model_source,
        model_ref=model_ref,
        messages=messages,
        temperature=0.0,
        max_tokens=_MAX_OUTPUT_TOKENS,
    )
    llm_output = response.content.strip()

    # 5. Guardrails — rejects rather than retries at MVP level.
    reject_reason = _guardrail_reject_reason(llm_output)
    if reject_reason is not None:
        logger.warning(
            "K20.1 regen rejected by guardrail: reason=%s user_id=%s "
            "scope=%s:%s",
            reject_reason, user_id, scope_type, scope_id,
        )
        return RegenerationResult(
            status="no_op_guardrail",
            skipped_reason=f"Regenerated content failed quality guardrail: {reject_reason}.",
        )

    # 6. Diversity check — skip write if >95% similar to current content.
    if current is not None:
        similarity = _jaccard_similarity(llm_output, current.content)
        if similarity > _SIMILARITY_NO_OP_THRESHOLD:
            return RegenerationResult(
                status="no_op_similarity",
                summary=current,
                skipped_reason=(
                    "New summary would be nearly identical to the "
                    "current version; no update written."
                ),
            )

    # 6b. Past-version dup check (K20.6). If the LLM just regenerated
    #     content that matches any of the last N archived versions,
    #     writing a new row would be churn without new information.
    #     Only fire this check when `current` exists — the history
    #     table is always empty before the first upsert. Same 0.95
    #     threshold as the primary similarity gate to keep the
    #     reject-surface consistent.
    if current is not None:
        past_versions = await ctx.summaries_repo.list_versions(
            user_id, scope_type, scope_id, limit=_PAST_VERSION_DUP_CHECK_LIMIT,
        )
        for past in past_versions:
            if (
                _jaccard_similarity(llm_output, past.content)
                > _SIMILARITY_NO_OP_THRESHOLD
            ):
                logger.info(
                    "K20.6 regen rejected: matches past version %d "
                    "(scope=%s:%s)",
                    past.version, scope_type, scope_id,
                )
                return RegenerationResult(
                    status="no_op_guardrail",
                    skipped_reason=(
                        f"Regenerated content duplicates past version "
                        f"{past.version}; no new history row written."
                    ),
                )

    # 7. Persist with the version guard. `edit_source='regen'`
    #    distinguishes our history rows from user manual edits so the
    #    30-day user_edit_lock fires only on *manual* edits (H1 fix).
    try:
        if scope_type == "project":
            assert scope_id is not None
            new_summary = await ctx.summaries_repo.upsert_project_scoped(
                user_id,
                scope_id,
                llm_output,
                expected_version=expected_version,
                edit_source="regen",
            )
        else:
            new_summary = await ctx.summaries_repo.upsert(
                user_id,
                "global",
                None,
                llm_output,
                expected_version=expected_version,
                edit_source="regen",
            )
    except VersionMismatchError:
        return RegenerationResult(
            status="regen_concurrent_edit",
            skipped_reason=(
                "A concurrent manual edit bumped the summary version "
                "during regeneration. Retry to include the newer content."
            ),
        )

    if new_summary is None:
        # Only reachable for the project path when the user doesn't
        # own `scope_id`. Router-level ownership is checked upstream,
        # so surfacing this as a guardrail no-op is safer than 500.
        return RegenerationResult(
            status="no_op_guardrail",
            skipped_reason="Summary write rejected: project ownership check failed.",
        )

    # 8. K20.7 / D-K20α-01 — record cost + token usage. Metrics are
    #    only incremented on the happy path because the LLM call
    #    was the only reason we spent money; no-op branches reject
    #    before step 4 or skip the write after. Token usage is a
    #    reliable counter even for models where pricing.py falls
    #    back to the default rate.
    usage = response.usage
    if usage.prompt_tokens:
        summary_regen_tokens_total.labels(
            scope_type=scope_type, token_kind="prompt",
        ).inc(usage.prompt_tokens)
    if usage.completion_tokens:
        summary_regen_tokens_total.labels(
            scope_type=scope_type, token_kind="completion",
        ).inc(usage.completion_tokens)
    cost_usd = _compute_llm_cost_usd(response, model_ref)
    if cost_usd > 0:
        summary_regen_cost_usd_total.labels(scope_type=scope_type).inc(
            float(cost_usd)
        )

    return RegenerationResult(status="regenerated", summary=new_summary)


async def regenerate_global_summary(
    *,
    user_id: UUID,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    pool: asyncpg.Pool,
    session_factory: Any,
    provider_client: ProviderClient,
    summaries_repo: SummariesRepo,
    trigger: RegenTrigger = "manual",
) -> RegenerationResult:
    """K20.2 — regenerate the user's L0 global bio.

    Reads raw global-scope chat turns (`project_id IS NULL`), calls
    the user's BYOK model with the L0 system prompt, runs drift +
    quality guardrails, and writes the result as a new `global`-scope
    summary version on success.
    """
    ctx = _RegenContext(
        pool=pool,
        session_factory=session_factory,
        provider_client=provider_client,
        summaries_repo=summaries_repo,
    )
    return await _regenerate_core(
        ctx,
        user_id=user_id,
        scope_type="global",
        scope_id=None,
        model_source=model_source,
        model_ref=model_ref,
        source_types=["chat_turn"],
        trigger=trigger,
    )


async def regenerate_project_summary(
    *,
    user_id: UUID,
    project_id: UUID,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    pool: asyncpg.Pool,
    session_factory: Any,
    provider_client: ProviderClient,
    summaries_repo: SummariesRepo,
    trigger: RegenTrigger = "manual",
) -> RegenerationResult:
    """K20.1 — regenerate a project's L1 summary.

    Reads raw project-scoped chat turns + chapter passages, calls the
    user's BYOK model with the L1 system prompt, runs drift + quality
    guardrails, and writes the result via `upsert_project_scoped`
    (which carries its own ownership check).
    """
    ctx = _RegenContext(
        pool=pool,
        session_factory=session_factory,
        provider_client=provider_client,
        summaries_repo=summaries_repo,
    )
    return await _regenerate_core(
        ctx,
        user_id=user_id,
        scope_type="project",
        scope_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        source_types=["chat_turn", "chapter"],
        trigger=trigger,
    )
