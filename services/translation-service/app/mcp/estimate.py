"""S-TRANSL cost-estimate (HIGH#1) + re-price-at-execution (H14).

A Tier-W translation job is *priced* — the agent MUST be able to tell the user
"this will cost ~$X" BEFORE confirming, and the service MUST NOT silently
overspend if the real cost drifts up between propose and execution.

This module owns the projection:

  1. **Source tokens** — sum `chapter_segments.token_estimate` over the job's
     scope. Two scopes:
       - whole-chapter(s): every segment of each requested chapter.
       - dirty/needs set (retranslate-dirty): only the segments that `needs`
         re-translation (source-dirty ∪ glossary-stale), via `compute_segment_status`.
  2. **Output tokens** — projected as `input * transl_estimate_output_ratio`
     (translation output ≈ source length). The ratio is config, NOT a model/price
     literal — pricing itself comes ENTIRELY from provider-registry.
  3. **Money** — `POST /internal/billing/estimate` (the SAME pure pricing oracle
     `app/workers/cost.py` uses for actuals, so an estimate and the live cost can
     never disagree on the price function). The model (`model_source`/`model_ref`)
     is resolved from the user's effective settings — never hardcoded.

`estimate_job_cost` returns a structured dict the confirm-token binds and the
agent renders. `reprice_exceeds_threshold` is the H14 gate: re-confirm when the
fresh actual estimate exceeds the confirmed estimate by BOTH a relative AND an
absolute floor (the design's "> est×1.25 OR > est+$0.50").

Identity/ownership is enforced by the MCP tool layer (require_book_owner) BEFORE
this runs; this module assumes the caller may act on the book.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from uuid import UUID

import asyncpg
import httpx
from loreweave_internal_client import build_internal_client

from ..config import settings
from ..effective_settings import resolve_effective_settings
from ..workers.segment_status import compute_segment_status

log = logging.getLogger(__name__)

_TIMEOUT = 5.0  # seconds (build_internal_client takes a float, not httpx.Timeout)

# Scope kinds the estimate understands.
SCOPE_CHAPTERS = "chapters"
SCOPE_DIRTY = "dirty"


@dataclass(frozen=True)
class CostEstimate:
    """A projected token + money cost for a translation job scope.

    `priced` is False (with `cost_usd=None`) when pricing couldn't be resolved
    (no model configured, an unpriced model, or provider-registry unreachable) —
    the agent still surfaces the token projection + a "cost unknown" caveat rather
    than a fabricated number or a hard failure. `model_source`/`model_ref` are the
    resolved effective model the estimate priced against (echoed so the confirm
    token binds the exact model the projection assumed)."""

    scope: str  # "chapters" | "dirty"
    target_language: str
    chapter_count: int
    segment_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    priced: bool
    model_source: str | None
    model_ref: str | None
    currency: str = "USD"

    def as_dict(self) -> dict:
        return asdict(self)


async def _sum_chapter_tokens(
    db: asyncpg.Pool, chapter_ids: list[UUID]
) -> tuple[int, int]:
    """(total token_estimate, segment_count) over EVERY segment of the chapters."""
    if not chapter_ids:
        return 0, 0
    row = await db.fetchrow(
        "SELECT COALESCE(SUM(token_estimate), 0) AS toks, COUNT(*) AS segs "
        "FROM chapter_segments WHERE chapter_id = ANY($1::uuid[])",
        list(chapter_ids),
    )
    return int(row["toks"] or 0), int(row["segs"] or 0)


async def _sum_dirty_tokens(
    db: asyncpg.Pool, chapter_id: UUID, target_language: str
) -> tuple[int, int]:
    """(token_estimate of the NEEDS set, needs-segment count) for one chapter+lang.
    `needs` = source-dirty ∪ glossary-stale — the exact set retranslate-dirty
    re-runs, so the estimate matches what will actually be spent."""
    items = await compute_segment_status(db, chapter_id, target_language)
    needed = [it for it in items if it["needs"]]
    return sum(int(it["token_estimate"] or 0) for it in needed), len(needed)


async def _price_tokens(
    *, owner_user_id: str, model_source: str | None, model_ref: str | None,
    input_tokens: int, output_tokens: int,
) -> float | None:
    """Price (input, output) tokens via provider-registry's pure estimate oracle —
    the SAME call `cost.py` uses for actuals. None on missing model / unpriced /
    non-200 / transport failure (the estimate degrades to 'cost unknown')."""
    if not model_source or not model_ref:
        return None
    if input_tokens <= 0 and output_tokens <= 0:
        return None
    base = settings.provider_registry_internal_url.rstrip("/")
    url = f"{base}/internal/billing/estimate"
    body = {
        "owner_user_id": owner_user_id,
        "items": [{
            "label": "translation",
            "model_source": model_source,
            "model_ref": str(model_ref),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
        }],
    }
    try:
        async with build_internal_client(settings.provider_registry_internal_url, internal_token=settings.internal_service_token, timeout_s=_TIMEOUT) as client:
            resp = await client.post(
                url, json=body,
            )
        if resp.status_code != 200:
            log.debug("billing/estimate %d for model %s", resp.status_code, model_ref)
            return None
        items = resp.json().get("items") or []
        if not items:
            return None
        item = items[0]
        if item.get("status") != "ok":
            # unpriced / not_found / bad_request → no money figure (still show tokens).
            return None
        usd = item.get("estimated_usd")
        return float(usd) if usd is not None else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.debug("billing/estimate resolve failed for %s: %s", model_ref, exc)
        return None


async def estimate_job_cost(
    db: asyncpg.Pool,
    *,
    owner_user_id: str,
    book_id: UUID,
    chapter_ids: list[UUID],
    scope: str = SCOPE_CHAPTERS,
    chapter_id: UUID | None = None,
    target_language: str | None = None,
    bound_model_source: str | None = None,
    bound_model_ref: str | None = None,
) -> CostEstimate:
    """Project the token + money cost of a translation job.

    - `scope=chapters` (start_job): price EVERY segment of `chapter_ids`.
    - `scope=dirty` (retranslate-dirty): price only the NEEDS segments of the
      single `chapter_id`.

    The target language comes from the user's settings (resolved here, never
    hardcoded); a caller-supplied `target_language` overrides for the estimate
    (mirrors how the job overlays it). Output tokens are projected at the
    configured output:input ratio. Money is None when unpriced (caveat, not error).

    Model binding (H14 / review-impl): at PROPOSE time the model is resolved from
    effective settings and ECHOED into the estimate (`model_source`/`model_ref`),
    then BOUND into the confirm token. At CONFIRM-time re-price the caller passes
    `bound_model_*` so the re-price prices the SAME model the user approved — NOT
    whatever effective settings now say (a settings flip between propose and
    confirm must not silently re-price a different model). When `bound_model_*` is
    given it takes precedence over the freshly-resolved effective model."""
    eff, _is_default, _updated = await resolve_effective_settings(
        UUID(owner_user_id), book_id, db
    )
    lang = target_language or eff.get("target_language") or "en"
    if bound_model_source is not None or bound_model_ref is not None:
        # Confirm-time re-price: honor the model the user approved at propose time.
        model_source = bound_model_source
        model_ref = bound_model_ref
    else:
        model_source = eff.get("model_source")
        model_ref = eff.get("model_ref")

    if scope == SCOPE_DIRTY:
        if chapter_id is None:
            raise ValueError("scope=dirty requires chapter_id")
        input_tokens, segment_count = await _sum_dirty_tokens(db, chapter_id, lang)
        chapter_count = 1
    else:
        input_tokens, segment_count = await _sum_chapter_tokens(db, chapter_ids)
        chapter_count = len(chapter_ids)

    output_tokens = int(round(input_tokens * settings.transl_estimate_output_ratio))

    cost_usd = await _price_tokens(
        owner_user_id=owner_user_id,
        model_source=model_source,
        model_ref=str(model_ref) if model_ref else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    return CostEstimate(
        scope=scope,
        target_language=lang,
        chapter_count=chapter_count,
        segment_count=segment_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        priced=cost_usd is not None,
        model_source=model_source,
        model_ref=str(model_ref) if model_ref else None,
    )


def reprice_exceeds_threshold(
    estimated_usd: float | None, actual_usd: float | None
) -> bool:
    """H14 re-price gate: should we REFUSE-and-re-confirm because the fresh actual
    estimate has drifted up past tolerance over the confirmed estimate?

    Trip iff actual > estimate*mult  OR  actual > estimate + abs
    (the design's "actual > est×1.25 OR > est+$0.50"). Both floors are config.

    Conservative on unknowns: if we couldn't re-price (`actual_usd is None`) we do
    NOT trip — a missing re-price must not block a confirmed cheap job (the job
    runs under the user's BYOK budget guard regardless). If there was no confirmed
    estimate (`estimated_usd is None`) but we now CAN price a real cost, trip so the
    user re-confirms against a real number (we never had a baseline to honor).

    Zero/near-zero baseline (`estimated_usd <= 0`, e.g. a $0.00 confirmed cost from
    a free/unpriced-as-zero model): the RELATIVE arm collapses to a $0.00 ceiling and
    would trip on ANY positive cent, defeating the absolute allowance. So with a
    non-positive baseline ONLY the absolute floor governs (a small dollar drift over
    $0.00 is tolerable; a drift past +$0.50 re-confirms). This keeps the est=0.0 case
    DISTINCT from est=None (no baseline → trip on any real cost)."""
    if actual_usd is None:
        return False
    if estimated_usd is None:
        # No baseline was shown to the user, but now there's a real cost → re-confirm.
        return actual_usd > 0.0
    abs_ceiling = estimated_usd + settings.transl_reprice_abs_usd
    if estimated_usd <= 0.0:
        # Degenerate relative ceiling — the absolute floor alone is meaningful.
        return actual_usd > abs_ceiling
    mult_ceiling = estimated_usd * settings.transl_reprice_mult
    return actual_usd > mult_ceiling or actual_usd > abs_ceiling
