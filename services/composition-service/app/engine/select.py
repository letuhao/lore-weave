"""Internal diverge→converge selection (V1 Phase A1, F3 — the highest-yield core).

Evidence-backed (Re3 rerank: +14% coherence vs single-draft): generate K candidate
continuations as blocking completions, then an LLM reranker picks the best against
coherence + premise/canon relevance. Distinct from the co-write STREAM path
(`cowrite.stream_draft`, which shows ONE draft to the human) — this is the AUTO
selection used when the loop, not a human, is the converge step.

Cost discipline (spec review H2 / §9 D1): K is the ONLY multiplied call; the
downstream canon-check + critic (A2) run on the WINNER only. Graceful degrade:
≥1 candidate or the step raises; a malformed/absent rerank → candidate[0].

Metering (enrichment lesson): completions here are non-stream, so there is no
UsageEvent — char-estimate the output (over-estimating; never meter 0). The
budget pre-check covers K candidates up front.

De-bias (§2.6): reuses `cowrite.build_messages` (language + abstract operation
steer, no English-only phrases) for drafting; the rerank rubric is abstract +
source-language-aware.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.cowrite import DraftMetering, build_messages, char_estimate
from app.engine.critic import parse_critique_json
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

# Disable hidden thinking on reasoning-model drafters/judges (the working knob for
# LM Studio + Qwen3.6; chat_template_kwargs kept for models that honor the flag).
_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}


@dataclass
class Candidate:
    text: str
    metering: DraftMetering


@dataclass
class Selection:
    winner: Candidate
    winner_index: int
    candidates: list[Candidate]
    rerank_reason: str
    rerank_measured: bool  # True = the reranker actually chose; False = fell back to [0]


async def _one_draft(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, str]], prompt_est: int, max_tokens: int,
    temperature: float, reasoning_effort: str | None, trace_id: str | None,
) -> Candidate | None:
    """One blocking draft completion. Returns None (dropped) on error / non-completed
    / empty output — diverge keeps the survivors."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
                "response_format": {"type": "text"},
                **({"reasoning_effort": reasoning_effort} if reasoning_effort is not None else _NO_THINK),
            },
            job_meta={"usage_purpose": "prose_draft", "extractor": "diverge_draft"}, trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("diverge draft LLM error: %s", exc)
        return None
    if job.status != "completed":
        logger.info("diverge draft status=%s → dropped", job.status)
        return None
    text = extract_judge_content(job.result)
    if not text.strip():
        return None
    # D-COMP-TRUNCATION-SURFACING: the gateway aggregator stamps finish_reason on
    # the job result ("length" ⇒ hit the output cap). Carry it on the metering.
    finish_reason = (job.result or {}).get("finish_reason")
    return Candidate(
        text=text,
        metering=DraftMetering(prompt_est, char_estimate(text), measured=False,
                               finish_reason=finish_reason),
    )


async def diverge(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    packed_prompt: str, profile: BookProfile, operation: str, guide: str,
    k: int, prompt_est: int, max_tokens: int, temperature: float = 0.8,
    reasoning_effort: str | None = None, trace_id: str | None = None,
) -> list[Candidate]:
    """K parallel draft completions of the SAME grounded prompt; diversity comes
    from temperature > 0 (Re3). Raises if zero candidates survive."""
    messages = build_messages(packed_prompt, profile, operation, guide)
    tasks = [
        _one_draft(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            messages=messages, prompt_est=prompt_est, max_tokens=max_tokens,
            temperature=temperature, reasoning_effort=reasoning_effort, trace_id=trace_id,
        )
        for _ in range(max(1, k))
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    cands = [r for r in results if isinstance(r, Candidate)]
    if not cands:
        raise RuntimeError("diverge produced no candidates")
    return cands


def build_rerank_prompt(candidates: list[Candidate], profile: BookProfile) -> tuple[str, str]:
    """Abstract, source-language-aware rerank rubric (Re3: coherence + premise/canon
    relevance). NO English-only illustrative phrases."""
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the reason in the language with code '{profile.source_language}'."
    )
    system = (
        "You are a fiction editor selecting the best of several drafted continuations. "
        "Judge each on coherence (logical flow), premise/canon relevance (fits the "
        "grounding and contradicts nothing established), and prose quality. Return ONLY "
        'a JSON object {"best": <0-based index>, "ranking": [indices best-first], '
        '"reason": str}.' + lang
    )
    body = "\n\n".join(f"[CANDIDATE {i}]\n{c.text}" for i, c in enumerate(candidates))
    return system, f"Select the single best continuation.\n\n{body}"


async def score(
    judge: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    candidates: list[Candidate], profile: BookProfile, max_tokens: int = 512,
    trace_id: str | None = None,
) -> tuple[int, str, bool]:
    """Rerank → (winner_index, reason, measured). measured=False (→ index 0) on a
    single candidate or any failure/malformed verdict (never raises)."""
    if len(candidates) <= 1:
        return 0, "single_candidate", False
    system, user = build_rerank_prompt(candidates, profile)
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": "prose_rerank", "extractor": "rerank"}, trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("rerank degraded (LLM error): %s → candidate[0]", exc)
        return 0, "rerank_unavailable", False
    if job.status != "completed":
        return 0, f"rerank_{job.status}", False
    parsed = parse_critique_json(extract_judge_content(job.result)) or {}
    best = parsed.get("best")
    # bool is an int subclass — exclude; bound-check against the candidate count.
    if isinstance(best, bool) or not isinstance(best, int) or not (0 <= best < len(candidates)):
        logger.info("rerank malformed best=%r → candidate[0]", best)
        return 0, "rerank_malformed", False
    reason = parsed.get("reason")
    return best, (reason if isinstance(reason, str) else ""), True


async def select_draft(
    llm: LLMClient, judge: LLMClient, *, user_id: str,
    drafter_source: str, drafter_ref: str, judge_source: str, judge_ref: str,
    packed_prompt: str, profile: BookProfile, operation: str, guide: str,
    k: int, prompt_est: int, max_tokens: int, temperature: float = 0.8,
    reasoning_effort: str | None = None, trace_id: str | None = None,
) -> Selection:
    """diverge(k) → score → Selection. The auto-loop's converge step; the winner
    is what A2's canon-check + critic then run on."""
    cands = await diverge(
        llm, user_id=user_id, model_source=drafter_source, model_ref=drafter_ref,
        packed_prompt=packed_prompt, profile=profile, operation=operation, guide=guide,
        k=k, prompt_est=prompt_est, max_tokens=max_tokens, temperature=temperature,
        reasoning_effort=reasoning_effort, trace_id=trace_id,
    )
    idx, reason, measured = await score(
        judge, user_id=user_id, model_source=judge_source, model_ref=judge_ref,
        candidates=cands, profile=profile, trace_id=trace_id,
    )
    return Selection(
        winner=cands[idx], winner_index=idx, candidates=cands,
        rerank_reason=reason, rerank_measured=measured,
    )
