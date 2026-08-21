"""knowledge-service's call-profile registry — one row per kind of LLM call it makes.

Same split the repo already uses twice (composition-service, lore-enrichment-service) and
that `PASS_REGISTRY` used before any of them: the SDK (`loreweave_llm.budget.call_budget`)
owns the MECHANISM — what an output kind means, how a target is sized, how reasoning eats the
same allowance — and the per-operation facts live here, beside the code that knows them.

What this service had instead
-----------------------------
THREE hand-rolled sizers, in three modules, none aware of the others:

    passages.py       _rerank_max_tokens(n)  = max(32, 8 + 5n)
    motif_tag.py      _max_tokens_for(n)     = 256 + 48n
    thread_tag.py     _max_tokens_for(n)     = 256 + 48n     (a byte-identical copy)

That is a second sizing model — with no floor, no reasoning allowance, and no context-window
clamp — plus a duplicate of it. The per-item SHAPE each encoded was real and is preserved as
the row's `target`; what they were missing is everything the SDK's model does around it.

`ceiling` is not decoration
---------------------------
`rerank_passages` is the row that proves it. Its budget was tiny ON PURPOSE: the call runs
under a 1.0s timeout, deliberately tighter than the L3 timeout that wraps it, and the cap is
what stops a rambling model from spending that second. Adopting the STRUCTURED floor (4096)
without a ceiling would have quietly removed a LATENCY control while looking like a safe
upgrade — the exact shape of the `compress` row in composition's registry, where raising a
budget silently raises the output it exists to bound.
"""
from __future__ import annotations

from dataclasses import dataclass

from loreweave_llm.budget import CallBudget, OutputKind, call_budget

__all__ = ["CallProfile", "unusable", "PROFILES", "budget_for", "max_tokens_for", "profile_for"]


@dataclass(frozen=True)
class CallProfile:
    kind: OutputKind
    #: The measured minimum for this call.
    floor: int
    #: The budget ACTUALLY IN USE before this row existed. For a row replacing a per-item
    #: formula this is the formula at its SMALLEST batch, so "adoption is never a downgrade"
    #: is true for every batch that ever ran, not just a typical one.
    was: int
    #: A static upper bound. `None` ⇒ the SDK's runaway guard. A row whose ceiling is per-call
    #: (see `rerank_passages`) passes it at the call site instead, where the count lives.
    ceiling: int | None = None
    why: str = ""


PROFILES: dict[str, CallProfile] = {
    # ── ranking / verdicts ────────────────────────────────────────────────────────────────
    # STRUCTURED: the reply is `{"order": [...]}` and a clipped array is unparseable, not
    # short. The ceiling is supplied PER CALL (`8 + 5n`) because it is a latency control tied
    # to the passage count, not a static size guess — see the module docstring.
    "rerank_passages": CallProfile(OutputKind.STRUCTURED, floor=32, was=32,
                                   why="a listwise reorder of n passages, under a 1s timeout"),
    # A `{"same": bool, "why": str}` object, but read with a tolerant extractor and degraded to
    # None on anything unparseable — a clipped reason still leaves a usable verdict. VERDICT.
    "coref_verdict": CallProfile(OutputKind.VERDICT, floor=1536, was=200,
                                 why="one same/different verdict for one candidate pair"),

    # ── per-batch classification: both replaced `256 + 48n`, in two modules, identically ──
    "motif_tag": CallProfile(OutputKind.STRUCTURED, floor=4096, was=304,
                             why="one motif code per event in the batch"),
    "thread_tag": CallProfile(OutputKind.STRUCTURED, floor=4096, was=304,
                              why="one thread key per event in the batch"),

    # ── extraction ────────────────────────────────────────────────────────────────────────
    "causal_edges": CallProfile(OutputKind.STRUCTURED, floor=4096, was=800,
                                why="cause/effect edges within one event window"),
    "backfill_event_status": CallProfile(OutputKind.STRUCTURED, floor=4096, was=2048,
                                         why="a status row per event in the backfill batch"),

    # ── prose ─────────────────────────────────────────────────────────────────────────────
    "regenerate_summary": CallProfile(OutputKind.PROSE, floor=1024, was=500,
                                      why="one regenerated chapter/arc summary"),
    "pdf_page_caption": CallProfile(OutputKind.PROSE, floor=1024, was=700,
                                    why="one caption for one PDF page image"),
    "wiki_article": CallProfile(OutputKind.PROSE, floor=4000, was=4000,
                                why="one generated wiki article"),
    # The KG schema proposal — a whole entity/relation schema object in one response.
    # Reached through the SDK's `structured_generate`, which now REQUIRES a CallBudget rather
    # than an int: a required int still let every caller invent its own number.
    "schema_propose": CallProfile(OutputKind.STRUCTURED, floor=4096, was=3000,
                                  why="one proposed KG schema object"),
    # The working-memory executive rewrites a session's charter+state as JSON. No
    # `response_format` is sent (lm_studio rejects json_object), so the prompt asks for JSON
    # and the code extracts it defensively — but the extraction still needs a COMPLETE object,
    # so truncation destroys the update rather than shortening it.
    "working_memory_executive": CallProfile(OutputKind.STRUCTURED, floor=4096, was=500,
                                            why="the rewritten charter + state object"),
}


def profile_for(code: str) -> CallProfile:
    try:
        return PROFILES[code]
    except KeyError:
        raise KeyError(
            f"no call profile for {code!r} — add a row to app/llm_budget.py rather than "
            f"passing a literal max_tokens"
        ) from None


def budget_for(code: str, *, target: int | None = None, language: str | None = None,
               reasoning=None, context_length: int | None = None,
               ceiling: int | None = None) -> CallBudget:
    """Resolve `code`'s budget, threading whatever per-call signal the caller holds.

    A call-site `ceiling` overrides the row's, for the one case where the bound is a function
    of the batch rather than a constant.
    """
    p = profile_for(code)
    kw = {}
    resolved_ceiling = ceiling if ceiling is not None else p.ceiling
    if resolved_ceiling is not None:
        kw["ceiling"] = resolved_ceiling
    return call_budget(
        p.kind, target=target, language=language, reasoning=reasoning,
        context_length=context_length, floor=p.floor, **kw,
    )


def max_tokens_for(code: str, **kw) -> int:
    """The `max_tokens` value for the wire."""
    return budget_for(code, **kw).max_output_tokens


def unusable(job, code: str) -> str | None:
    """Why this job's output must not be used — or ``None`` when it is fine.

    Folds TWO questions, and every call site here already asked one of them. ``status !=
    "completed"`` was checked everywhere; ``finish_reason == "length"`` was checked almost
    nowhere — measured 2026-08-03, **2 of 28** STRUCTURED call sites, while the spec's S7
    asked for exactly this ("and on a missing ``finish_reason == 'length'`` check").

    They are the same question. The SDK already decides which kinds care —
    ``truncation_is_fatal = (kind is OutputKind.STRUCTURED)`` — because a JSON or
    grammar-constrained response **cannot stop early in a valid place**: a clipped array is
    either unparseable or, worse, parseable with items silently missing. For those kinds a
    truncated job is exactly as unusable as one that never completed, so it takes the branch
    the site already wrote and needs no new judgement.

    NOT fatal for PROSE / EDIT / VERDICT / MIRROR, and that is deliberate rather than lenient.
    A clipped paragraph is short, not wrong. A clipped verdict fails to parse into a verdict
    the caller already treats as absent, and `judge_plan_conflicts` reports that absence
    through its `judged` flag — the fix for the incident that motivated all of this. Making
    those fatal would convert working degradations into outages.

    Returns a SHORT reason (``"status=failed"`` / ``"truncated"``) rather than a bool, because
    several call sites fold it into a log line or an error code — a sentence there would turn an
    error code into a paragraph. The long explanation belongs here, not in every caller.
    """
    status = getattr(job, "status", None)
    if status != "completed":
        # The bare status, not `f"status={status}"`. Two call sites fold this straight into an
        # error CODE (`error=f"audit_{why}"`), and a test pinned `audit_failed` — so the
        # prefixed form silently renamed a code that something downstream may key on. The new
        # state simply joins the same vocabulary as `audit_truncated`.
        return str(status or "unknown")
    # The RESOLVED budget, not the kind. The kind is only the default: a row may ESCALATE
    # (`truncation_fatal=True`) when its output is a LIST that truncation destroys while its
    # sizing is verdict-shaped. Asking the kind here left `cross_scene_check` uncovered after
    # its row had already declared the fatality — one rule, two places, and they disagreed
    # within an hour. `budget_for` is pure arithmetic, so resolving it here is free.
    if getattr(job, "finish_reason", None) == "length" and budget_for(code).truncation_is_fatal:
        return "truncated"
    return None
