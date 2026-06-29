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
from collections.abc import Awaitable, Callable
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
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
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
            job_meta={"usage_purpose": "promise_audit", "extractor": "promise_audit"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("promise_audit LLM error: %s", exc)
        return _shape([], [], [], error="audit_unavailable")
    if getattr(job, "status", None) != "completed":
        return _shape([], [], [], error=f"audit_{getattr(job, 'status', None)}")
    return _parse_audit(extract_judge_content(job.result))


# ── EVAL v2 — fixed-promise-set coverage (FD-8 follow-up) ─────────────────────
# The v1 dropped-promise-RATE had an unstable denominator: each arm's `introduced`
# list was model-volunteered, so re-injection inflating how many promises the ON
# arm surfaces shifted the rate (introduced-inflation confound). v2 fixes a SINGLE
# tracked-promise set derived from the premise+plan (the SPEC, NOT either arm's
# prose), then scores both arms against that identical set — apples-to-apples,
# denominator-stable. It also separates ABANDONED (introduced then never
# referenced again = a real drop) from PROGRESSING (still live at the cutoff =
# sustained tension, NOT a drop) — the v1 metric mislabeled sustained tension as
# dropped on truncated arcs.

_VERDICTS = ("paid", "progressing", "abandoned", "absent")


def build_extract_messages(premise: str, plan_text: str, source_language: str) -> tuple[str, str]:
    """(system, user) — derive the tracked-promise set from the SPEC (premise +
    outline plan), never from generated prose, so it is identical for both arms."""
    lang = "" if source_language in ("", "auto") else (
        f" Write each promise in the language with code '{source_language}'."
    )
    system = (
        "You read a story's PREMISE and OUTLINE and list the narrative PROMISES it "
        "sets up — the setups that create an expectation of a later payoff "
        "(foreshadowings, open questions, stated goals, threats, mysteries, "
        "unresolved conflicts). List ONLY promises implied by the premise/outline "
        "themselves, not ones a particular telling might add. Return ONLY a JSON "
        'object {"promises": [str, ...]}, each a short phrase.' + lang
    )
    user = f"PREMISE:\n{premise}\n\n---\n\nOUTLINE:\n{plan_text}"
    return system, user


def build_coverage_messages(promises: list[str], arc_text: str, source_language: str) -> tuple[str, str]:
    """(system, user) — score each FIXED promise against one arc's prose."""
    lang = "" if source_language in ("", "auto") else (
        f" Write nothing but the JSON; verdicts are the fixed English tokens below."
    )
    numbered = "\n".join(f"{i}. {p}" for i, p in enumerate(promises))
    system = (
        "You are given a fixed list of narrative PROMISES and a STORY. For EACH "
        "promise, judge how the story handles it and assign exactly one verdict:\n"
        "- \"paid\": the promise is clearly resolved/paid off in the text.\n"
        "- \"progressing\": introduced and actively advanced, but still open at the "
        "end (sustained tension, NOT abandoned).\n"
        "- \"abandoned\": introduced/referenced once, then never developed or paid.\n"
        "- \"absent\": the story never engages this promise at all.\n"
        "Judge only from the text. Return ONLY a JSON object "
        '{"verdicts": [{"index": int, "verdict": "paid"|"progressing"|"abandoned"|"absent"}, ...]} '
        "with one entry per promise index." + lang
    )
    user = f"PROMISES:\n{numbered}\n\n---\n\nSTORY:\n{arc_text}"
    return system, user


def _coverage_shape(promises: list[str], verdicts: list[str], error: str | None = None) -> dict[str, Any]:
    """Aggregate per-promise verdicts → counts + the v2 rates. `introduced` = the
    fixed-set promises the arm actually engages (paid+progressing+abandoned);
    `absent` is excluded from the rate denominators (the arm never picked it up).
    Both arms share the SAME fixed promise set, so the rates are comparable even
    though `introduced` may differ — that difference is itself a signal."""
    pairs = list(zip(promises, verdicts))
    n = {v: sum(1 for _, x in pairs if x == v) for v in _VERDICTS}
    introduced = n["paid"] + n["progressing"] + n["abandoned"]
    out: dict[str, Any] = {
        "coverage": [{"promise": p, "verdict": v} for p, v in pairs],
        "tracked_count": len(promises),
        "introduced_count": introduced,
        "paid_count": n["paid"],
        "progressing_count": n["progressing"],
        "abandoned_count": n["abandoned"],
        "absent_count": n["absent"],
        # pay = resolved; sustained = paid OR still-live (NOT a drop); abandon = the
        # real drop. Guarded against div-by-zero (no introduced → 0.0).
        "pay_rate": (n["paid"] / introduced) if introduced else 0.0,
        "sustained_rate": ((n["paid"] + n["progressing"]) / introduced) if introduced else 0.0,
        "abandon_rate": (n["abandoned"] / introduced) if introduced else 0.0,
    }
    if error is not None:
        out["error"] = error
    return out


def _parse_coverage(content: str, promises: list[str]) -> dict[str, Any]:
    """Tolerant parse → per-promise verdict aligned to the fixed promise list by
    index. Missing/garbled entries default to 'absent' (the arm gets no credit for
    a promise the judge couldn't verify — conservative, never fabricates a pay)."""
    obj = parse_critique_json(content) or {}
    by_index: dict[int, str] = {}
    for e in (obj.get("verdicts") or []):
        if not isinstance(e, dict):
            continue
        idx, verd = e.get("index"), e.get("verdict")
        if isinstance(idx, int) and verd in _VERDICTS:
            by_index[idx] = verd
    verdicts = [by_index.get(i, "absent") for i in range(len(promises))]
    return _coverage_shape(promises, verdicts)


async def _chat(llm, *, user_id, model_source, model_ref, system, user, max_tokens, trace_id, tag,
                cancel_check: Callable[[], Awaitable[bool]] | None = None):
    """Shared single-shot, reasoning-disabled, degrade-safe call. Returns the
    parsed content string, or None on LLM/non-completed failure."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": "promise_audit", "extractor": tag}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("%s LLM error: %s", tag, exc)
        return None
    if getattr(job, "status", None) != "completed":
        logger.warning("%s non-completed: %s", tag, getattr(job, "status", None))
        return None
    return extract_judge_content(job.result)


async def extract_tracked_promises(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    premise: str, plan_text: str, source_language: str = "auto",
    max_tokens: int = 800, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[str]:
    """Derive the fixed tracked-promise set from premise+plan. Returns [] on
    failure (the harness then skips the book rather than scoring a phantom set)."""
    system, user = build_extract_messages(premise, plan_text, source_language)
    content = await _chat(llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
                          system=system, user=user, max_tokens=max_tokens, trace_id=trace_id,
                          tag="promise_extract", cancel_check=cancel_check)
    if content is None:
        return []
    obj = parse_critique_json(content) or {}
    return _str_list(obj.get("promises"))


async def score_promise_coverage(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    promises: list[str], arc_text: str, source_language: str = "auto",
    max_tokens: int = 1500, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Score one arc's prose against the FIXED promise set. On failure returns the
    all-'absent' shape + `error` (never raises)."""
    if not promises:
        return _coverage_shape([], [], error="no_tracked_promises")
    system, user = build_coverage_messages(promises, arc_text, source_language)
    content = await _chat(llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
                         system=system, user=user, max_tokens=max_tokens, trace_id=trace_id,
                         tag="promise_coverage", cancel_check=cancel_check)
    if content is None:
        return _coverage_shape(promises, ["absent"] * len(promises), error="coverage_unavailable")
    return _parse_coverage(content, promises)
