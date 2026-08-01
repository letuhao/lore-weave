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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loreweave_llm import ReasoningDirective, no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.cowrite import (
    DEFAULT_SCENE_TARGET_WORDS,
    MEASURED_SINGLE_CALL_CEILING_WORDS,
    DraftMetering,
    beat_targets,
    build_beat_scope,
    build_messages,
    char_estimate,
    realised_words,
    repeated_span_chars,
    scene_output_budget,
)
from app.engine.critic import parse_critique_json
from app.packer.profile import BookProfile
from app.reasoning import wire_fields
from app.llm_budget import max_tokens_for

logger = logging.getLogger(__name__)


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
    # ── D-SCENE-BEATS slice 2 — how the winner's TEXT was produced. Defaulted so every
    # existing construction (and `select_draft`) is unchanged: one call, one passage.
    #: "single_call" = one draft call. "per_beat" = the scene's `draft_beats` drafted in
    #: order, each continuing the last, joined.
    #:
    #: Deliberately NOT called `assembly_mode`, and deliberately not sharing its values.
    #: `assembly_mode` is an AUTHORED work setting with a closed set (`per_scene|chapter`),
    #: a settings dropdown, and a PATCH validator: it answers "did you ask for a scene or a
    #: chapter?". This answers "how many calls made the text?". Two questions, two names —
    #: the rule that renamed `beats` to `draft_beats` one commit ago.
    #:
    #: Not "…_stitch" either: `per_scene_stitch` names an LLM merge pass, and there is none
    #: here (see `select_scene` for why there must not be).
    scene_assembly: str = "single_call"
    beats_drafted: int = 1
    #: What each passage actually yielded, in order — the measurement, not an intention.
    beat_words: list[int] = field(default_factory=list)
    #: Chars of a passage that appeared VERBATIM in an earlier one. The per-beat prompt
    #: forbids repetition; this is whether it obeyed. An observation, never a blocker.
    repeated_chars: int = 0
    #: Declared beats that produced no passage (a mid-scene failure, partial-saved). >0 means
    #: the scene is INCOMPLETE against its plan — a fact the envelope must carry, because the
    #: text alone reads like a finished short scene.
    beats_failed: int = 0
    #: Passages asked for more words than one call is measured to deliver
    #: (`MEASURED_SINGLE_CALL_CEILING_WORDS`). Advisory: the engine does NOT re-split an
    #: author's declared passages, because that would silently overrule authored intent. But a
    #: scene that comes back at 60% of its target for this reason must be able to SAY so —
    #: otherwise it looks like the same mystery shortfall that took a false diagnosis and two
    #: commits to explain.
    beats_over_ceiling: int = 0


async def _one_draft(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, str]], prompt_est: int, max_tokens: int,
    temperature: float, reasoning: ReasoningDirective | None, trace_id: str | None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> Candidate | None:
    """One blocking draft completion. Returns None (dropped) on error / non-completed
    / empty output — diverge keeps the survivors."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
                "response_format": {"type": "text"},
                # Both knobs or neither. The old form sent a bare `reasoning_effort` and
                # dropped `chat_template_kwargs`, so an effort resolved for a template-driven
                # local model only half-applied.
                **wire_fields(reasoning),
            },
            job_meta={"usage_purpose": "prose_draft", "extractor": "diverge_draft"}, trace_id=trace_id,
            cancel_check=cancel_check,
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
    reasoning: ReasoningDirective | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    target_words: int | None = None, beat_scope: str | None = None,
) -> list[Candidate]:
    """K parallel draft completions of the SAME grounded prompt; diversity comes
    from temperature > 0 (Re3). Raises if zero candidates survive.

    ``target_words`` threads a scene LENGTH directive into the prompt (else the drafter free-runs
    short — the auto-worker path is the one that actually drafts a scene, so it MUST carry it).
    ``beat_scope`` narrows the draft to one of the scene's beats (D-SCENE-BEATS slice 2)."""
    messages = build_messages(packed_prompt, profile, operation, guide,
                              target_words=target_words, beat_scope=beat_scope)
    tasks = [
        _one_draft(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            messages=messages, prompt_est=prompt_est, max_tokens=max_tokens,
            temperature=temperature, reasoning=reasoning, trace_id=trace_id,
            cancel_check=cancel_check,
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
    candidates: list[Candidate], profile: BookProfile, max_tokens: int | None = None,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[int, str, bool]:
    """Rerank → (winner_index, reason, measured). measured=False (→ index 0) on a
    single candidate or any failure/malformed verdict (never raises)."""
    if len(candidates) <= 1:
        return 0, "single_candidate", False
    # Resolved here, not as a default argument, because the candidate count is a per-call
    # fact and a default is frozen at import. The response is
    # `{"best": int, "ranking": [one entry per candidate], "reason": str}` and the reason has
    # to justify a choice among all of them, so it grows with the count — `language` because
    # a Vietnamese reason costs 2.6 tokens/word against English's 1.7, and VERDICT is one of
    # the two branches that actually reads it.
    max_tokens = max_tokens or max_tokens_for(
        "select_score", target=len(candidates), language=profile.source_language)
    system, user = build_rerank_prompt(candidates, profile)
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens, **no_thinking_fields(),
            },
            job_meta={"usage_purpose": "prose_rerank", "extractor": "rerank"}, trace_id=trace_id,
            cancel_check=cancel_check,
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
    reasoning: ReasoningDirective | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    target_words: int | None = None, beat_scope: str | None = None,
) -> Selection:
    """diverge(k) → score → Selection. The auto-loop's converge step; the winner
    is what A2's canon-check + critic then run on.

    D-LENGTH-DIRECTIVE-NEVER-SENT (2026-07-31). ``target_words`` did not exist on this
    function. `diverge` accepted it, `build_messages` rendered it, a unit test proved the
    rendering — and this, the ONLY route to a per-scene draft (both the inline auto path and
    the worker's `run_generate`), dropped it on the floor. So the LENGTH directive was
    computed, written into `job.input["target_words"]`, used to size `max_output_tokens`, and
    then never put in the prompt. Only the chapter single-pass (`run_chapter_generate`, which
    calls `diverge` directly) ever carried it.

    That is the honest explanation of the measurements this feature was designed from: asks
    of 200 and 1500 words both came back ~560, `finish_reason="stop"`, across two models. Not
    a model ceiling, not a beat's material running out — **the model was never told a
    length**. A correct function plus a unit test proving the function is correct is not
    coverage of the path; nothing asserted the directive reached a draft CALL.
    """
    cands = await diverge(
        llm, user_id=user_id, model_source=drafter_source, model_ref=drafter_ref,
        packed_prompt=packed_prompt, profile=profile, operation=operation, guide=guide,
        k=k, prompt_est=prompt_est, max_tokens=max_tokens, temperature=temperature,
        reasoning=reasoning, trace_id=trace_id, cancel_check=cancel_check,
        target_words=target_words, beat_scope=beat_scope,
    )
    idx, reason, measured = await score(
        judge, user_id=user_id, model_source=judge_source, model_ref=judge_ref,
        candidates=cands, profile=profile, trace_id=trace_id, cancel_check=cancel_check,
    )
    return Selection(
        winner=cands[idx], winner_index=idx, candidates=cands,
        rerank_reason=reason, rerank_measured=measured,
    )


async def select_scene(
    llm: LLMClient, judge: LLMClient, *, user_id: str,
    drafter_source: str, drafter_ref: str, judge_source: str, judge_ref: str,
    packed_prompt: str, profile: BookProfile, operation: str, guide: str,
    k: int, prompt_est: int, max_tokens: int,
    draft_beats: list[dict[str, Any]] | None = None,
    target_words: int | None = None,
    temperature: float = 0.8,
    reasoning: ReasoningDirective | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> Selection:
    """Draft a whole SCENE — in one call, or one call per declared beat (D-SCENE-BEATS).

    ``draft_beats`` empty (every scene authored before this feature) ⇒ exactly `select_draft`,
    one call, unchanged. Non-empty ⇒ each beat is drafted in order, each call seeing the
    passages already written, and the results joined.

    **Sequential, not parallel.** K parallel beat calls would be N× faster and each one would
    write the scene's opening, re-introduce the cast, and re-establish the setting — which is
    why the beat prompt carries the prose so far and why this loop awaits.

    **Joined, not stitched.** `stitch_chapter` exists because scene drafts are written blind
    to each other and need an LLM merge pass. These are not blind — beat i read beats 1..i-1 —
    so a merge pass would buy continuity that is already there at the price of one more
    full-length call through the step where prose most often gets compressed away.

    Partial-save on a mid-scene failure. If beat 3 dies after 1 and 2 succeeded, the prose
    that was paid for is returned with ``beats_failed`` set rather than discarded; only a
    failure on the FIRST beat raises, because then there is nothing to keep. This mirrors the
    stream path's budget-exhaustion partial-save.
    """
    lang = profile.source_language
    # A declared passage COUNTS even with no brief in it: `[{}, {}]` says "write this scene in
    # two calls", which is a complete instruction on its own. Filtering falsy entries here —
    # the first version of this line did — silently collapsed that to a single call and looked
    # exactly like the feature not working. A malformed (non-dict) entry keeps its slot for the
    # same reason: losing a passage is worse than losing a brief.
    beats: list[dict[str, Any]] = []
    for b in draft_beats or []:
        if isinstance(b, dict):
            beats.append(b)
        else:
            logger.warning("draft_beats entry %r is not an object — drafting it with no brief", b)
            beats.append({})
    scene_target = int(target_words or DEFAULT_SCENE_TARGET_WORDS)

    if not beats:
        sel = await select_draft(
            llm, judge, user_id=user_id,
            drafter_source=drafter_source, drafter_ref=drafter_ref,
            judge_source=judge_source, judge_ref=judge_ref,
            packed_prompt=packed_prompt, profile=profile, operation=operation, guide=guide,
            k=k, prompt_est=prompt_est, max_tokens=max_tokens, temperature=temperature,
            reasoning=reasoning, trace_id=trace_id, cancel_check=cancel_check,
            target_words=scene_target,
        )
        sel.beat_words = [realised_words(sel.winner.text, lang)[0]]
        # The single-call scene is where this matters MOST: a 2500-word target in one call
        # lands at ~61% with `finish="stop"`, which looks like nothing is wrong. Saying it here
        # is the difference between "the model wrote short" and "you asked one call for more
        # than one call delivers — declare passages".
        sel.beats_over_ceiling = int(scene_target > MEASURED_SINGLE_CALL_CEILING_WORDS)
        return sel

    targets = beat_targets(beats, scene_target)
    over_ceiling = sum(1 for t in targets if t > MEASURED_SINGLE_CALL_CEILING_WORDS)
    if over_ceiling:
        logger.info("%d of %d passages ask for more than one call delivers (>%d words) — "
                    "the scene will land short of its target", over_ceiling, len(targets),
                    MEASURED_SINGLE_CALL_CEILING_WORDS)
    parts: list[str] = []
    words: list[int] = []
    reasons: list[str] = []
    finishes: list[str | None] = []
    in_tok = out_tok = repeated = 0
    measured_all = True
    rerank_all = True
    last: Selection | None = None

    for i, beat in enumerate(beats):
        written = "\n\n".join(parts)
        # Per-beat ceiling, narrowed within the scene's: a runaway beat must not eat the
        # room the later ones need. An explicit caller `max_tokens` still bounds it.
        cap = min(max_tokens, scene_output_budget(targets[i], lang, reasoning=reasoning))
        try:
            sel = await select_draft(
                llm, judge, user_id=user_id,
                drafter_source=drafter_source, drafter_ref=drafter_ref,
                judge_source=judge_source, judge_ref=judge_ref,
                packed_prompt=packed_prompt, profile=profile, operation=operation, guide=guide,
                k=k, prompt_est=prompt_est, max_tokens=cap, temperature=temperature,
                reasoning=reasoning, trace_id=trace_id, cancel_check=cancel_check,
                target_words=targets[i],
                beat_scope=build_beat_scope(index=i, total=len(beats), beat=beat,
                                            written_so_far=written),
            )
        except Exception as exc:  # noqa: BLE001 — see the partial-save note above
            if not parts:
                raise
            logger.warning("beat %d/%d of scene draft failed: %s — keeping the %d passage(s) "
                           "already written", i + 1, len(beats), exc, len(parts))
            break
        text = sel.winner.text
        repeated += repeated_span_chars(written, text)
        parts.append(text)
        words.append(realised_words(text, lang)[0])
        in_tok += sel.winner.metering.input_tokens
        out_tok += sel.winner.metering.output_tokens
        measured_all = measured_all and sel.winner.metering.measured
        rerank_all = rerank_all and sel.rerank_measured
        finishes.append(sel.winner.metering.finish_reason)
        if sel.rerank_reason:
            reasons.append(f"beat{i + 1}: {sel.rerank_reason}")
        last = sel

    failed = len(beats) - len(parts)
    if len(parts) == 1 and last is not None:
        # One passage — the beat's own candidates ARE scene alternatives, so keep them
        # (and the judge's real pick). Only a MULTI-beat scene has to collapse them.
        last.scene_assembly = "per_beat"
        last.beats_drafted = 1
        last.beat_words = words
        last.repeated_chars = 0
        last.beats_failed = failed
        last.beats_over_ceiling = over_ceiling
        return last

    winner = Candidate(
        text="\n\n".join(parts),
        metering=DraftMetering(
            input_tokens=in_tok, output_tokens=out_tok, measured=measured_all,
            # "length" if ANY passage was cut off — one truncated passage truncates the scene.
            finish_reason="length" if "length" in finishes else (finishes[-1] if finishes else None),
        ),
    )
    return Selection(
        winner=winner, winner_index=0,
        # NOT the last beat's candidates. A candidate there is ONE passage of N; handing it
        # to an author as an alternative SCENE would be a lie about what they are choosing
        # between. A multi-beat scene has exactly one assembled draft, and says so.
        candidates=[winner],
        rerank_reason=" · ".join(reasons), rerank_measured=rerank_all,
        scene_assembly="per_beat", beats_drafted=len(parts), beat_words=words,
        repeated_chars=repeated, beats_failed=failed, beats_over_ceiling=over_ceiling,
    )
