"""FD-1 S4b — dropped-promise-rate audit (the discriminating eval signal, §8).

A holistic LLM pass over a FULL generated arc that re-detects the narrative
promises in the PROSE and judges which were paid off: returns introduced /
resolved / dropped lists + counts + `dropped_rate`.

CRITICAL (anti-self-reinforcement, lesson `eval-self-reinforcement`): this audit
re-detects promises FROM THE TEXT — it MUST NOT read the `narrative_thread`
ledger. The eval runs the SAME audit over both arms (ledger-ON and ledger-OFF);
if it read the ledger the OFF arm would score 0-introduced by construction (a
fake win). The arm comparison is only valid because detection is ledger-blind.

Server-side (an internal endpoint), same rationale as `eval_judge`: the only
host-accessible LLM path is the chat-service SSE, so the harness reuses the
composition LLMClient + gateway here as a single POST→audit. The prompt is
server-controlled; only the arc text + the judge model are caller-supplied. The
caller picks a judge model DISTINCT from the drafter (§4); this fn does not
enforce it. The arc prose IS the measurement, so it is NOT sanitized (sanitizing
would corrupt the count) — the prompt delimits it robustly, mirroring
`pairwise_judge`.
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


def build_audit_messages(arc_text: str, source_language: str) -> tuple[str, str]:
    """(system, user). Abstract + source-language-aware (no English-only
    illustrative phrases — the CJK-bias lesson)."""
    lang = "" if source_language in ("", "auto") else (
        f" Write each `text` field in the language with code '{source_language}'."
    )
    system = (
        "You audit a complete story for NARRATIVE PROMISES and whether they pay "
        "off. A promise is any setup that creates an expectation of a later payoff: "
        "a foreshadowing, an open question, a stated goal or intention, a threat, a "
        "mystery, an unresolved conflict, a Chekhov's-gun detail. For the WHOLE "
        "text, list: (1) every promise INTRODUCED, (2) those later RESOLVED/paid "
        "off, (3) those left DROPPED (introduced but never paid off by the end). A "
        "promise resolved is NOT also dropped. Judge only from the text itself. "
        "Return ONLY a JSON object "
        '{"introduced": [str, ...], "resolved": [str, ...], "dropped": [str, ...]}, '
        "each entry a short phrase naming the promise." + lang
    )
    user = f"STORY:\n{arc_text}"
    return system, user


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [s.strip() for s in raw if isinstance(s, str) and s.strip()]


def _shape(introduced: list[str], resolved: list[str], dropped: list[str],
           error: str | None = None) -> dict[str, Any]:
    """Assemble the audit result + the derived rate. `dropped_rate` =
    dropped / introduced, guarded against div-by-zero (0 introduced → 0.0, a
    story with no promises has no dropped-promise problem) AND clamped to [0,1]
    (review-impl MED#1): the LLM's `dropped` list is not enforced ⊆ `introduced`,
    so a stray extra entry must not push the headline rate above 1 and skew the
    n-book mean. resolved/dropped are informational; the rate keys off the model's
    explicit `dropped` list."""
    intro_n = len(introduced)
    out: dict[str, Any] = {
        "introduced": introduced, "resolved": resolved, "dropped": dropped,
        "introduced_count": intro_n,
        "resolved_count": len(resolved),
        "dropped_count": len(dropped),
        "dropped_rate": min(1.0, len(dropped) / intro_n) if intro_n else 0.0,
    }
    if error is not None:
        out["error"] = error
    return out


def _parse_audit(content: str) -> dict[str, Any]:
    """Tolerant parse → the audit shape. A garbled audit yields empty lists
    (→ rate 0.0), never a crash."""
    obj = parse_critique_json(content) or {}
    return _shape(
        _str_list(obj.get("introduced")),
        _str_list(obj.get("resolved")),
        _str_list(obj.get("dropped")),
    )


async def audit_promises(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    arc_text: str, source_language: str = "auto",
    max_tokens: int = 1500, trace_id: str | None = None,
) -> dict[str, Any]:
    """Audit one arc's promises. On any LLM/parse failure returns empty lists +
    `error` (never raises — an eval that errors must not fabricate a count)."""
    system, user = build_audit_messages(arc_text, source_language)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"extractor": "promise_audit"}, trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("promise_audit LLM error: %s", exc)
        return _shape([], [], [], error="audit_unavailable")
    if getattr(job, "status", None) != "completed":
        return _shape([], [], [], error=f"audit_{getattr(job, 'status', None)}")
    return _parse_audit(extract_judge_content(job.result))
