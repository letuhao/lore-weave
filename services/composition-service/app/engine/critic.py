"""judge_prose advisory critic (§4) — 4 dims + per-violation canon check.

Reuses the eval client (the JudgeLLMClient Protocol is satisfied by our
LLMClient) with `operation="chat"`. The critic model MUST differ from the
drafter (anti-self-reinforcement §4) — the CALLER passes a distinct model_ref.

Tolerance (enrichment repair.py lesson): the model returns JSON; we strip
fences + extract the first balanced object, then read dims defensively and
FILTER malformed `violations[]` per-item — one bad verdict never discards the
whole critique. CC4: any LLM/timeout error degrades to an empty advisory
critique (the critic is advisory; it must NEVER block accept).

De-bias (§2.6): the rubric judges in the book's `source_language`; prompts use
abstract phrasing, NO English-only illustrative phrases (memory: those bias a
CJK/VN judge to English).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

_DIMENSIONS = ("coherence", "voice_match", "pacing", "canon_consistency")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_critique_json(text: str) -> dict[str, Any] | None:
    """Strip code fences + extract the first balanced {...} object. None on
    hard failure (the caller degrades — never raises)."""
    if not text:
        return None
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError):
        pass
    # Fallback: first balanced top-level object.
    depth = 0
    start = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(cleaned[start:i + 1])
                except (ValueError, TypeError):
                    return None
    return None


def _coerce_score(value: Any) -> int | None:
    """A dim score is an int 0-5; anything else → None (unjudged on that dim)."""
    if isinstance(value, bool):  # bool is an int subclass — exclude
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 5 else None
    if isinstance(value, float) and value.is_integer():
        v = int(value)
        return v if 0 <= v <= 5 else None
    return None


def _filter_violations(raw: Any) -> list[dict[str, Any]]:
    """Keep only well-formed violation verdicts (dict with a rule_id). A
    malformed item is dropped, not fatal (tolerant parse)."""
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for v in raw:
        if not isinstance(v, dict) or v.get("rule_id") in (None, ""):
            continue
        out.append({
            "rule_id": str(v.get("rule_id")),
            "violated": bool(v.get("violated", True)),
            "span": v.get("span") if isinstance(v.get("span"), str) else "",
            "why": v.get("why") if isinstance(v.get("why"), str) else "",
        })
    return out


def normalize_critique(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Shape a parsed judge response into the generation_job.critic contract.
    Missing/malformed dims → None; malformed violations filtered out."""
    parsed = parsed or {}
    crit: dict[str, Any] = {d: _coerce_score(parsed.get(d)) for d in _DIMENSIONS}
    crit["violations"] = _filter_violations(parsed.get("violations"))
    return crit


def build_critique_prompt(
    passage: str, active_rules: list[dict[str, Any]], present_facts: list[str],
    profile: BookProfile,
) -> tuple[str, str]:
    """Build (system, user) for judge_prose. Abstract, multilingual-safe rubric
    (no English-only illustrative phrases). The judge scores in source_language
    when known."""
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write all string values in the language with code '{profile.source_language}'."
    )
    system = (
        "You are a fiction continuity and craft critic. Judge the passage on four "
        "dimensions, each an integer 0-5: coherence (logical flow), voice_match "
        "(consistency with the work's voice), pacing (fit to the scene's beat), and "
        "canon_consistency (does it contradict any active canon rule or established "
        "fact). For each active rule the passage contradicts, add a violation with "
        "its rule_id, a short contradicting span, and why. Return ONLY a JSON object "
        '{"coherence":int,"voice_match":int,"pacing":int,"canon_consistency":int,'
        '"violations":[{"rule_id":str,"violated":true,"span":str,"why":str}]}.'
        + lang
    )
    rules_block = "\n".join(f'- [{r.get("rule_id")}] {r.get("text", "")}' for r in active_rules) or "(none)"
    facts_block = "\n".join(f"- {f}" for f in present_facts) or "(none)"
    user = (
        f"ACTIVE CANON RULES:\n{rules_block}\n\n"
        f"ESTABLISHED FACTS (present entities):\n{facts_block}\n\n"
        f"PASSAGE:\n{passage}"
    )
    return system, user


async def judge_prose(
    judge: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    passage: str, active_rules: list[dict[str, Any]], present_facts: list[str],
    profile: BookProfile, max_tokens: int = 1536, trace_id: str | None = None,
) -> dict[str, Any]:
    """Run the advisory critique. Returns the generation_job.critic dict. CC4:
    any LLM/timeout/parse failure degrades to an empty critique with an `error`
    marker — NEVER raises (advisory must not block accept)."""
    system, user = build_critique_prompt(passage, active_rules, present_facts, profile)
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens,
                # Disable hidden thinking: reasoning_effort="none" is the knob
                # that actually works for LM Studio + Qwen3.6 (chat_template_kwargs
                # alone is a no-op there). The critic emits JSON, so reasoning
                # tokens are pure budget-burn. Kept chat_template_kwargs for models
                # that honor the template flag instead.
                "reasoning_effort": "none",
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            job_meta={"usage_purpose": "prose_critic", "extractor": "judge_prose"}, trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("judge_prose degraded (LLM error): %s", exc)
        return {**{d: None for d in _DIMENSIONS}, "violations": [], "error": "critic_unavailable"}
    if job.status != "completed":
        logger.info("judge_prose job status=%s → degraded", job.status)
        return {**{d: None for d in _DIMENSIONS}, "violations": [], "error": f"critic_{job.status}"}
    content = extract_judge_content(job.result)
    return normalize_critique(parse_critique_json(content))
