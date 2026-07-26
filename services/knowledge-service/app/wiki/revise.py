"""Wiki bounded revise — one verify-driven re-generation (wiki-llm M4 / §C4).

After generate (M3) + verify (M4), if the article tripped a HIGH flag or the
auto-reject (publish-blocked), do ONE corrective re-generation that feeds the
verify flags back to the LLM, then re-verify and **keep-if-improved** (the result
with FEWER flags wins; a tie keeps the original — a revise never makes it worse).
A revise that fails to generate cleanly keeps the original. Bounded at one extra
LLM call so a pathological entity can't loop.
"""

from __future__ import annotations

import logging

from app.clients.book_profile_client import BookProfile
from app.clients.llm_client import LLMClient
from app.wiki.context import GenerationContext
from app.wiki.generate import GenerateResult, generate_article
from app.wiki.verify import WikiVerifyResult, verify_article

logger = logging.getLogger(__name__)

__all__ = ["should_revise", "is_improved", "revise_article"]


def should_revise(verify: WikiVerifyResult) -> bool:
    """Revise only when it's worth a second LLM call: a HIGH-severity flag fired
    or the article is publish-blocked (auto-rejected). A clean / soft-only result
    is kept as-is."""
    return verify.has_high or verify.publish_blocked


def is_improved(new: WikiVerifyResult, old: WikiVerifyResult) -> bool:
    """Whether a revised verify result is BETTER than the original (keep-if-improved).

    Publish-block-aware so a revise can never make the outcome worse — a flag
    COUNT alone would wrongly accept a revision that trades several soft flags for
    one severe (newly publish-blocking) flag. Rules, in order:
      * a revision that becomes publish-blocked when the original wasn't → NOT improved;
      * clearing a publish-block → ALWAYS improved;
      * same block status → strictly fewer flags wins (ties keep the original).
    """
    if new.publish_blocked and not old.publish_blocked:
        return False
    if old.publish_blocked and not new.publish_blocked:
        return True
    return new.flag_count < old.flag_count


def _verify_corrective(verify: WikiVerifyResult) -> str:
    """A concise note feeding the verify flags back to the LLM for the re-gen."""
    issues = "; ".join(
        f"[{f['kind']}/{f['dimension']}] {f['evidence']}" for f in verify.flags
    )
    return (
        "Your previous draft was flagged by canon-verification: "
        f"{issues}. Revise to REMOVE these issues — do not contradict the "
        "entity's established canon, avoid out-of-era/anachronistic terms, do NOT "
        "copy source wording verbatim (paraphrase), and keep every claim cited."
    )


async def revise_article(
    *,
    gen: GenerateResult,
    verify: WikiVerifyResult,
    context: GenerationContext,
    profile: BookProfile,
    llm: LLMClient,
    user_id: str,
    model_source: str,
    model_ref: str,
    max_tokens: int | None = None,
    temperature: float = 0.3,
    # D-KG-WIKI-WORKER-GRADED-EFFORT — the revise IS a second prose-generation
    # pass, so it honors the same graded effort as the initial generate.
    reasoning_effort: str = "none",
) -> tuple[GenerateResult, WikiVerifyResult]:
    """One bounded, keep-if-improved revise pass.

    Returns the (gen, verify) pair to use downstream — the revised one ONLY when
    it has strictly fewer flags than the original; otherwise the original is kept.
    A no-op (nothing worth revising, or the original has no IR) returns the inputs
    unchanged."""
    if gen.ir is None or not should_revise(verify):
        return gen, verify

    kwargs: dict = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    gen2 = await generate_article(
        context=context, profile=profile, llm=llm, user_id=user_id,
        model_source=model_source, model_ref=model_ref,
        temperature=temperature,
        max_attempts=1,  # the revise itself is the bounded second pass
        initial_corrective=_verify_corrective(verify),
        reasoning_effort=reasoning_effort,
        **kwargs,
    )
    if gen2.status != "ok" or gen2.ir is None:
        logger.info("wiki revise produced no clean article (%s) — keeping original",
                    gen2.status)
        return gen, verify

    verify2 = await verify_article(gen2.ir, context, profile)
    if is_improved(verify2, verify):
        return gen2, verify2
    return gen, verify
