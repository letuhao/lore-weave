"""D-CANON-CHECK-SDK-UNIFY — shared symbolic-prefilter + LLM-judge plumbing.

Hoisted from two near-duplicate modules that grew independently:
`composition-service/app/engine/canon_check.py` (the original, checks a DRAFT
against the knowledge fact-for-check snapshot) and
`knowledge-service/app/extraction/canon_check.py` (a 2026-07-05 POC mirror,
checks CHAPTER TEXT being extracted against the KG's own gone-status). A
2026-07-06 diff of both found the pieces below byte-identical or
near-identical in shape; everything domain-specific (prompt wording, the
extra per-service candidate field, the top-level orchestration functions)
stays in each service's own `canon_check.py`, which imports this module for
the mechanical parts.

One real gap this unification fixes: the knowledge-service copy caught bare
`Exception` and manually indexed `job.result["messages"][0]["content"]`
instead of composition's more precise `LLMError` + `extract_judge_content`
handling. `extract_judge_text` below is that same load-bearing parsing logic
(memory: gateway responses are `messages[0].content`, not `result.content`),
now shared instead of re-invented per service.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

__all__ = [
    "SPAN_PAD",
    "find_span",
    "parse_judge_verdicts",
    "extract_judge_text",
    "build_judge_request",
    "judge_is_self",
    "apply_verdicts",
    "gone_entities_referenced",
    "CanonCandidateBase",
    "resolve_cast_liveness",
    "unresolved_cast_refs",
    "LIVENESS_ALIVE",
    "LIVENESS_GONE",
    "LIVENESS_UNKNOWN",
    "LIVENESS_SOURCE_KG",
    "LIVENESS_SOURCE_PLAN",
    "LIVENESS_SOURCE_NONE",
]

SPAN_PAD = 40  # chars of context either side of a match


def find_span(text: str, name: str, pad: int = SPAN_PAD) -> tuple[str, str] | None:
    """(matched_name, excerpt) if `name` occurs in `text`, else None. Word
    boundaries for ASCII names (avoids 'Al' matching inside 'Always'); plain
    lowercase containment for CJK/non-ASCII names (no \\b word boundary in
    CJK script)."""
    if not name or not name.strip():
        return None
    name = name.strip()
    idx = -1
    if name.isascii():
        m = re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE)
        if m:
            idx = m.start()
    else:
        idx = text.lower().find(name.lower())
    if idx < 0:
        return None
    start = max(0, idx - pad)
    end = min(len(text), idx + len(name) + pad)
    excerpt = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    return name, excerpt


def _balanced_json_objects(text: str) -> list[str]:
    """Every top-level balanced `{...}` substring in `text`, in order. A naive
    `first '{' .. last '}'` span breaks when a small local model "thinks out
    loud" and emits more than one JSON block in one response (observed live:
    a first, wrong `{"verdicts":[...]}` followed by prose starting with
    "Self-correction:" and a second, corrected block) — the naive span
    swallows the prose between them and fails to parse at all, silently
    discarding a perfectly good corrected answer. Scanning brace-by-brace
    (string-aware, so a `}` inside a quoted `why` doesn't miscount) isolates
    each object on its own."""
    objects: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        start = i
        while i < n:
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    objects.append(text[start:i + 1])
                    i += 1
                    break
            i += 1
        else:
            break  # unterminated object — stop scanning
    return objects


def repair_truncated_json(text: str) -> str | None:
    """Close a JSON object whose TAIL was cut off, or return None if nothing is salvageable.

    ⚠️ WHY THIS EXISTS, MEASURED. A live judge call (composition job `019ff401`, 2026-08-12)
    answered all twenty roles with reasons — `output_tokens: 684`, `finish_reason: "stop"` —
    and the reply was missing exactly ONE character: the closing brace of the outer object.
    `_balanced_json_objects` finds only BALANCED objects, so it yielded no candidates,
    `parse_judge_verdicts` returned `{}`, and the caller logged *"produced NO verdicts ... the
    role check did not run"*. Twenty good verdicts were discarded over one byte, and the
    session that investigated it concluded the judge model was incapable. It was not.

    The repair is deliberately CONSERVATIVE — it only ever CLOSES what is already open, and
    never invents a value:
      * if the text ends inside a string, cut back to before that string started;
      * cut back to the last completed array element / object member;
      * append the missing closers in reverse order of the open stack.
    A half-written final verdict is DROPPED rather than guessed, so a repaired reply is a
    strict prefix of what the model actually said.
    """
    if not text or "{" not in text:
        return None
    stack: list[str] = []
    in_string = False
    escape = False
    last_safe: int | None = None      # index AFTER the last completed element
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
                # A closed object/array sitting inside an array is a complete element.
                if stack and stack[-1] == "]":
                    last_safe = i + 1
            else:
                return None           # genuinely malformed, not merely truncated
    if not stack:
        return None                   # already balanced: nothing to repair
    # ⚠️ ALWAYS cut back to the last COMPLETED element — never merely close the brackets
    # where the text happens to stop.
    #
    # The first version of this function closed the open stack in place, which turned
    # `{"verdicts":[{"entity_id":"e1","violated":true` into a confident verdict for e1: a
    # half-written object completed by the parser rather than by the model. That is inventing
    # a value, which this function's own docstring forbids, and the pre-existing
    # `test_unterminated_json_degrades_to_empty` caught it immediately.
    if last_safe is None:
        return None                   # no complete element — nothing to salvage
    body = text[:last_safe]
    # Recompute the open stack for the TRUNCATED body — the stack from the full scan
    # describes brackets that the dropped tail may have opened.
    stack = []
    in_string = False
    escape = False
    for ch in body:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()
    return body + "".join(reversed(stack)) if stack else None


def parse_judge_verdicts(content: str) -> dict[str, dict[str, Any]]:
    """`{entity_id: {violated, why}}` from the judge's JSON reply; tolerant of
    a markdown fence, surrounding prose, and (see `_balanced_json_objects`)
    more than one JSON block in one response — takes the LAST block that
    parses into a `{"verdicts": [...]}` shape, treating a model's own
    self-correction as its final answer. Empty dict on any hard parse
    failure — the caller treats a missing entity_id as `confirmed=None`
    (advisory), never a crash."""
    if not content:
        return {}
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    obj = None
    for candidate in reversed(_balanced_json_objects(text)):
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and "verdicts" in parsed:
            obj = parsed
            break
    if obj is None:
        # Nothing balanced parsed. Before giving up — which the caller reports as "the judge
        # did not run" — try the truncated-tail repair. See `repair_truncated_json`: this is
        # the path that recovered 20 verdicts from a reply missing one closing brace.
        repaired = repair_truncated_json(text)
        if repaired is not None:
            try:
                parsed = json.loads(repaired)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict) and "verdicts" in parsed:
                obj = parsed
    if obj is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for v in (obj.get("verdicts") or []) if isinstance(obj, dict) else []:
        if isinstance(v, dict) and v.get("entity_id") is not None:
            out[str(v["entity_id"])] = {
                "violated": bool(v.get("violated", False)),
                "why": v.get("why") if isinstance(v.get("why"), str) else "",
            }
    return out


def extract_judge_text(result: dict[str, Any] | None) -> str:
    """Read a gateway completion's text from a terminal Job result.

    LOAD-BEARING: the content is at `result["messages"][0]["content"]`, NOT
    `result["content"]`. Returns "" when absent so a malformed/empty frame
    degrades to unjudged rather than crashing the caller."""
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages") or []
    if messages and isinstance(messages[0], dict):
        return messages[0].get("content", "") or ""
    return ""


def build_judge_request(
    messages: list[dict[str, str]],
    *,
    usage_purpose: str,
    extractor: str,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """The shared judge-call request shape (both services' proven degrade-safe
    defaults): text response format, temperature 0, thinking disabled. Returns
    `{"input": ..., "job_meta": ...}` — splat into `llm.submit_and_wait(...)`."""
    return {
        "input": {
            "messages": messages,
            "response_format": {"type": "text"},
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
        },
        "job_meta": {"usage_purpose": usage_purpose, "extractor": extractor},
    }


def judge_is_self(judge_ref: Any, subject_ref: Any) -> bool:
    """Is the model about to grade this the same model that PRODUCED it?

    Invariant 2 is *no model is silently its own judge*. Composition enforces it through
    `engine/critic_policy.py`, which resolves both refs to a provider identity — five
    `user_model_id` rows on one dev box are one gemma, so a ref comparison is the weaker test.

    This is the WEAKER test, and it lives here because knowledge-service needs it and cannot
    use the stronger one: its judge ref is whatever model ran the extraction, it has no
    `work.settings` to hold a critic, and it has no resolver wired. Ref-level catches the case
    that is actually happening there — the SAME ref on both sides — and misses two rows that
    are one model. Named so the difference is visible at the call site rather than assumed.

    Compared as strings because the two sides arrive differently typed: one comes off a job
    message and the other off a request body, so one may be a `UUID` and the other its text.
    An identity check between a `UUID` and its own `str` is False, which would report a model
    as an independent judge of its own output while every same-typed test stayed green.

    Missing on either side is NOT self-judging — it is unknown, and the caller must not read
    `False` as "verified independent". `judge_is_self(None, x)` is False for the same reason
    `CriticResolution.identity_verified` distinguishes `None` from `False`.
    """
    if not judge_ref or not subject_ref:
        return False
    return str(judge_ref).strip() == str(subject_ref).strip()


def apply_verdicts(candidates: list[Any], verdicts: dict[str, dict[str, Any]]) -> None:
    """Mutate each candidate's `confirmed`/`source`/`why` in place from the
    judge's verdict dict, keyed by `entity_id` (both services' candidate
    models carry this field). A candidate the judge omits is left untouched
    (`confirmed` stays whatever the caller set, normally None — advisory)."""
    for c in candidates:
        v = verdicts.get(c.entity_id)
        if v is not None:
            c.confirmed = v["violated"]
            c.source = "llm_judge"
            c.why = v["why"]


def gone_entities_referenced(
    text: str,
    snapshot: dict[str, Any] | None,
    *,
    extra_field: str | None = None,
) -> list[dict[str, Any]]:
    """Symbolic pre-filter: every `gone` entity in `snapshot` whose name (or
    canonical_name) appears in `text`. Empty when `text`/`snapshot` is absent
    (degrades to advisory — an outage never blocks). De-duped per entity (the
    first matching name form wins). Returns raw dicts (`entity_id`, `name`,
    `span`, `matched`, + `extra_field` if given) — each service wraps these
    into its own typed candidate model with its own extra domain field
    (composition: `glossary_entity_id`; knowledge: `gone_from_order`)."""
    if not text or not snapshot:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ent in snapshot.get("entities") or []:
        if not isinstance(ent, dict) or ent.get("status") != "gone":
            continue
        eid = ent.get("entity_id")
        if not eid or eid in seen:
            continue
        for name in (ent.get("name"), ent.get("canonical_name")):
            hit = find_span(text, name) if isinstance(name, str) else None
            if hit is None:
                continue
            matched, span = hit
            row: dict[str, Any] = {
                "entity_id": eid, "name": ent.get("name"),
                "span": span, "matched": matched,
            }
            if extra_field:
                row[extra_field] = ent.get(extra_field)
            out.append(row)
            seen.add(eid)
            break
    return out


class CanonCandidateBase(BaseModel):
    """The 8 fields both services' candidate models share. Each service
    subclasses this adding its own extra field and its own `kind` default
    (e.g. `kind: str = "gone_entity_present"`)."""

    kind: str
    source: str = "score_symbolic"   # vs "llm_judge"
    entity_id: str
    name: str | None = None
    status: str = "gone"
    span: str = ""                   # excerpt of the text around the match
    matched: str = ""                # the name form that matched
    confirmed: bool | None = None    # set by the judge; None = symbolic-only (advisory)
    why: str = ""


# ── S2 · one cast-liveness SSOT, per ENTITY ──────────────────────────────────────────────

#: What the platform can say about one cast member at one reading position.
#: `unknown` is not a failure state — it is the only honest answer when nothing in the corpus
#: mentions this entity, and it is DIFFERENT from `alive`.
LIVENESS_ALIVE = "alive"
LIVENESS_GONE = "gone"
LIVENESS_UNKNOWN = "unknown"

#: Which layer answered. `none` means nothing did.
LIVENESS_SOURCE_KG = "kg"
LIVENESS_SOURCE_PLAN = "plan"
LIVENESS_SOURCE_NONE = "none"


def resolve_cast_liveness(
    entity_ids: list[str] | tuple[str, ...],
    snapshot: dict[str, Any] | None,
    *,
    plan_status: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Per-ENTITY, per-FACT liveness. `{entity_id: {"status", "source"}}`.

    THE BUG THIS EXISTS FOR. `gone_entities_referenced` above answers one question — "which
    entities in the snapshot are marked gone and named in this text?" — and everything it does
    not return is treated by every caller as fine. So an entity the knowledge graph has NEVER
    HEARD OF takes the identical path to an entity the graph positively knows is alive. The
    guard cannot tell "this character is alive" from "this character does not exist", and the
    second is the interesting one: it is a reference to an undeclared identifier, which is what
    PF-1 named as *"anonymous characters were uses of undeclared identifiers"*.

    THE CASCADE is KG → plan → none, and it stops at the first layer that has an OPINION. A
    plan-level status is weaker evidence than the graph's, so it only speaks where the graph is
    silent; and when neither speaks the answer is `unknown`/`none` rather than a default.

    ⚠ THE FIXTURE THAT MATTERS is a NON-EMPTY snapshot with no row for the subject — not an
    empty snapshot. An empty one is indistinguishable from an outage and every implementation
    passes it, which is why the first version of this test would have gone green while the bug
    survived. A `None` snapshot here is an OUTAGE: everything is `unknown`/`none`, which is
    correct and is also why the caller must not read `unknown` as `gone`.
    """
    rows = (snapshot or {}).get("entities") or []
    by_id: dict[str, str] = {}
    for ent in rows:
        if not isinstance(ent, dict):
            continue
        eid, status = ent.get("entity_id"), ent.get("status")
        # A row with no status is a row with no OPINION — it must not shadow the plan layer.
        if eid and isinstance(status, str) and status:
            by_id[str(eid)] = status

    plan = {str(k): v for k, v in (plan_status or {}).items() if isinstance(v, str) and v}
    out: dict[str, dict[str, str]] = {}
    for raw in entity_ids or ():
        eid = str(raw)
        if eid in by_id:
            out[eid] = {"status": by_id[eid], "source": LIVENESS_SOURCE_KG}
        elif eid in plan:
            out[eid] = {"status": plan[eid], "source": LIVENESS_SOURCE_PLAN}
        else:
            out[eid] = {"status": LIVENESS_UNKNOWN, "source": LIVENESS_SOURCE_NONE}
    return out


def unresolved_cast_refs(liveness: dict[str, dict[str, str]]) -> list[str]:
    """The cast ids no layer could speak to. This is the eval's `unresolved_refs` signal, and
    it is a COUNT OF FACTS, not of failures — a book early in its life legitimately has many."""
    return sorted(k for k, v in (liveness or {}).items()
                  if v.get("source") == LIVENESS_SOURCE_NONE)
