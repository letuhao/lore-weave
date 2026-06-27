"""A-EVAL — pairwise longer-form judge (Re3/DOC method).

The Phase-A coherence-median gate SATURATES at 5/5 on short scenes (A1+A3 both),
so it can't validate "orchestrated reasoning beats V0". This is the discriminating
replacement: a judge reads TWO full chapter drafts and picks which is more
coherent/consistent (relative → no ceiling), plus per-draft DEFECT COUNTS
(continuity breaks / dropped threads / contradictions / repetition).

Server-side (an internal endpoint) rather than the eval script, because the only
host-accessible LLM path is the chat-service's stateful AG-UI SSE; reusing the
composition LLMClient + gateway here keeps the harness a single POST→verdict and
the model/auth path proven. The judge PROMPT is server-controlled (this is a
pairwise comparator, NOT a generic LLM proxy); only the two drafts + the model
are caller-supplied. The caller picks a DISTINCT judge model (anti-self-
reinforcement §4) — the eval passes the critic; this fn does not enforce it.

Drafts are labelled blind ("Draft 1" / "Draft 2"); the CALLER is responsible for
swapping order across samples to cancel position bias.
"""

from __future__ import annotations

import logging
from typing import Any

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.critic import parse_critique_json

logger = logging.getLogger(__name__)

_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}

_DEFECT_KEYS = ("continuity_breaks", "dropped_threads", "contradictions", "repetition")


def build_pairwise_messages(
    draft_a: str, draft_b: str, source_language: str,
) -> tuple[str, str]:
    """(system, user). Abstract + source-language-aware (no English-only
    illustrative phrases — the CJK-bias lesson)."""
    lang = "" if source_language in ("", "auto") else (
        f" Write the `why` field in the language with code '{source_language}'."
    )
    system = (
        "You compare two drafts of the same story chapter for narrative QUALITY. "
        "Judge which reads as more coherent and internally consistent across its "
        "full length — logical scene-to-scene flow, no continuity breaks, no "
        "contradictions, no dropped setups, minimal repetition. For EACH draft also "
        "count its defects. Return ONLY a JSON object "
        '{"better": "1" | "2" | "tie", "why": str, '
        '"defects_1": {"continuity_breaks": int, "dropped_threads": int, '
        '"contradictions": int, "repetition": int}, '
        '"defects_2": {"continuity_breaks": int, "dropped_threads": int, '
        '"contradictions": int, "repetition": int}}.' + lang
    )
    user = f"DRAFT 1:\n{draft_a}\n\n---\n\nDRAFT 2:\n{draft_b}"
    return system, user


def _coerce_defects(raw: Any) -> dict[str, int]:
    out = {k: 0 for k in _DEFECT_KEYS}
    if isinstance(raw, dict):
        for k in _DEFECT_KEYS:
            v = raw.get(k)
            if isinstance(v, bool):  # bool is an int subclass — exclude
                continue
            if isinstance(v, int) and v >= 0:
                out[k] = v
    return out


def _parse_verdict(content: str) -> dict[str, Any]:
    """Tolerant parse → {better, why, defects_1, defects_2}. `better` defaults to
    'tie' on a missing/garbled value (a malformed judge never crowns a winner)."""
    obj = parse_critique_json(content) or {}
    better = obj.get("better")
    if better not in ("1", "2", "tie"):
        better = "tie"
    why = obj.get("why")
    return {
        "better": better,
        "why": why if isinstance(why, str) else "",
        "defects_1": _coerce_defects(obj.get("defects_1")),
        "defects_2": _coerce_defects(obj.get("defects_2")),
    }


async def pairwise_judge(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    draft_a: str, draft_b: str, source_language: str = "auto",
    max_tokens: int = 1024, trace_id: str | None = None,
) -> dict[str, Any]:
    """Run the pairwise comparison. On any LLM/parse failure returns a 'tie'
    verdict with `error` set (never raises — an eval judge that errors must not
    fabricate a winner)."""
    system, user = build_pairwise_messages(draft_a, draft_b, source_language)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": "prose_eval", "extractor": "pairwise_judge"}, trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("pairwise_judge LLM error: %s", exc)
        return {"better": "tie", "why": "", "defects_1": _coerce_defects(None),
                "defects_2": _coerce_defects(None), "error": "judge_unavailable"}
    if getattr(job, "status", None) != "completed":
        return {"better": "tie", "why": "", "defects_1": _coerce_defects(None),
                "defects_2": _coerce_defects(None), "error": f"judge_{getattr(job, 'status', None)}"}
    return _parse_verdict(extract_judge_content(job.result))
