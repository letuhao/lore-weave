"""Chapter stitch pass (LOOM chapter-assembly-modes, B3).

The `per_scene` + stitch path: once a chapter's scenes are drafted, ONE LLM pass
merges the consecutive scene drafts into a single seamless chapter — removing
repeated introductions / echoed descriptions and smoothing transitions, while
changing NO plot facts. Degrade-safe: any failure returns "" so the caller falls
back to the raw concatenation (never blocks). The stitched output is re-checked
by the chapter-level canon guard (a rewrite can re-introduce a gone character).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.select import _NO_THINK
from app.packer.profile import BookProfile, style_directive

logger = logging.getLogger(__name__)


def cap_scene_drafts(drafts: list[str], max_chars: int) -> tuple[list[str], int]:
    """MED-3 input cap — char-cap with head+tail keep. Returns (kept, elided).

    Keeps the EARLIEST + LATEST scenes intact (opening + closing continuity, where
    stitching matters most) and elides the middle when the concatenation exceeds
    `max_chars`. Always keeps at least the first + last scene (so a very long
    chapter still stitches its ends rather than degrading entirely). `elided` is
    logged by the caller — no silent truncation."""
    if sum(len(d) for d in drafts) <= max_chars or len(drafts) <= 2:
        return list(drafts), 0
    head = [drafts[0]]
    tail = [drafts[-1]]
    budget = max_chars - len(drafts[0]) - len(drafts[-1])
    i, j = 1, len(drafts) - 2
    take_head = True
    while i <= j and budget > 0:
        d = drafts[i] if take_head else drafts[j]
        if len(d) > budget:
            break
        budget -= len(d)
        if take_head:
            head.append(d)
            i += 1
        else:
            tail.append(d)
            j -= 1
        take_head = not take_head
    kept = head + list(reversed(tail))
    return kept, len(drafts) - len(kept)


async def stitch_chapter(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    scene_drafts: list[str], chapter_intent: str, profile: BookProfile,
    max_tokens: int, max_input_chars: int,
    reasoning_effort: str | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[str, str | None]:
    """Merge the chapter's scene drafts into one seamless chapter. Returns
    ``(stitched_prose, finish_reason)`` — prose is "" on empty input / LLM failure
    / empty output (the caller degrades to the raw concatenation); finish_reason is
    the model's stop reason ("length" ⇒ the stitch hit the cap; None when degraded
    or unreported — D-COMP-TRUNCATION-SURFACING)."""
    drafts = [d for d in scene_drafts if d and d.strip()]
    if not drafts:
        return "", None
    kept, elided = cap_scene_drafts(drafts, max_input_chars)
    if elided:
        logger.info("stitch input capped: kept %d/%d scene drafts (elided %d middle)",
                    len(kept), len(drafts), elided)
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5 — chapter-scoped density/pace
    system = (
        "You are a fiction editor merging consecutive scene drafts of ONE chapter "
        "into a single seamless chapter. Remove repeated introductions and echoed "
        "descriptions, smooth the transitions between scenes, and keep one "
        "continuous narrative. Change NO plot facts, events, or dialogue meaning — "
        "only restructure and de-duplicate the prose. Output ONLY the chapter prose."
        + lang + voice + style
    )
    intent = (chapter_intent or "").strip()
    user = (f"Chapter intent: {intent}\n\n" if intent else "") + "\n\n".join(
        f"[SCENE {i + 1}]\n{d}" for i, d in enumerate(kept)
    )
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.3, "max_tokens": max_tokens,
                "response_format": {"type": "text"},
                **({"reasoning_effort": reasoning_effort} if reasoning_effort is not None else _NO_THINK),
            },
            job_meta={"usage_purpose": "prose_stitch", "extractor": "stitch_chapter"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("stitch LLM error: %s → degrade to raw concat", exc)
        return "", None
    if job.status != "completed":
        logger.info("stitch status=%s → degrade to raw concat", job.status)
        return "", None
    text = extract_judge_content(job.result)
    if not text.strip():
        return "", None
    return text, (job.result or {}).get("finish_reason")
