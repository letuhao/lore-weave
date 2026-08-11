"""D-W10-ARC-CONFORMANCE-SUCCESSION (Feature 2) — causal-edge inference over :Event.

Infers `(:Event)-[:CAUSES]->(:Event)` edges from the ordered timeline so deep
arc-conformance can upgrade a legal succession transition from *structural* (the order
respects the `precedes` graph) to *causally verified* (the prose actually shows motif A's
beat causing motif B's). The LLM reads a sliding WINDOW of ordered events and names which
earlier event directly causes/enables which later one (forward links only).

Cost is bounded by running ONLY over the caller-filtered event set (in practice the
motif-tagged subset — the arc-relevant beats), a window cap, and a hard window-count cap.

ADVISORY / UNCALIBRATED: NEVER raises — an outage / junk output yields fewer (or no) edges.
LLM via the SDK (`operation='chat'` → provider-registry; no provider SDK import; model_ref
passed in). Pure `build_messages` / `parse_edges` are the test surface.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from loreweave_llm.reasoning import ReasoningDirective, reasoning_fields

from app.llm_budget import unusable, max_tokens_for

logger = logging.getLogger(__name__)

# The two ordered edge kinds of the world partial order (plan T33 / D0.1-D8), plus the
# refusal. `causes` is a claim about WHY; `precedes` is a claim only about ORDER. They are
# different strengths of assertion and collapsing them loses the distinction a canon check
# needs — "B happened after A" is cheap and usually safe, "A caused B" is expensive and often
# wrong.
REL_CAUSES = "causes"
REL_PRECEDES = "precedes"
REL_UNKNOWN = "unknown"
_ORDERED_KINDS = (REL_CAUSES, REL_PRECEDES)

_SYSTEM_PROMPT = (
    "You are a narrative-order analyst. Given story EVENTS in reading order, you label the "
    "relation between an earlier and a later event as exactly one of: "
    "causes (the earlier event DIRECTLY brings about or enables the later one); "
    "precedes (the later event clearly happens after, but you cannot show causation); "
    "unknown (you cannot tell, or the events are unrelated). "
    "Only forward links (the earlier event must appear first). PREFER 'unknown' over guessing: "
    "a wrong order is worse than an absent one. Reply with STRICT JSON only: a list of "
    "[earlier_label, later_label, relation] triples, using the E-labels exactly as given. "
    "No prose, no code fence."
)

_WINDOW = 12          # events per LLM call
_STRIDE = 6           # overlap so a cross-boundary cause→effect isn't missed
_MAX_WINDOWS = 40     # hard cap on LLM calls per request (cost backstop)


def event_tokens(window: list[dict[str, Any]]) -> dict[str, str]:
    """PURE — `{"E1": <event id>, …}` for one window, in reading order.

    The handle the model is asked to answer with. See `build_messages` for why it
    is not the raw id.
    """
    return {f"E{i + 1}": e["id"] for i, e in enumerate(window)}


def build_messages(window: list[dict[str, Any]]) -> list[dict[str, str]]:
    """PURE — chat messages for one window of ORDERED events (``[{id,title,summary?}]``).

    Events are labelled `E1..En`, NOT by their raw id, and the listing carries no
    separate line number.

    MEASURED, and this is why the corpus bite kept returning zero. The listing used
    to read ``1. id=<32-hex> | title`` — a line NUMBER beside a long opaque id — and
    the model answered with the number:

        [[1, 2, unknown], [2, 3, precedes], [3, 6, causes], …]

    `parse_edges` then correctly dropped every triple, because `1` is not an event
    id in the window. The inference had worked; the handles did not survive the round
    trip, and the failure looked identical to "the model found nothing".

    One label per event, matching what the answer is asked to contain, removes the
    ambiguity — there is no second number on the line to answer with.
    """
    lines = []
    for i, e in enumerate(window):
        summ = (e.get("summary") or "").strip()
        lines.append(f"E{i + 1} | {e.get('title', '')}" + (f" — {summ}" if summ else ""))
    user = ("EVENTS in reading order:\n" + "\n".join(lines)
            + "\n\nReturn JSON [[earlier_label, later_label, relation], ...] using the "
              "E-labels exactly as written above (e.g. \"E1\"), with relation "
              "one of causes | precedes | unknown. Omit a pair entirely, or label it "
              "'unknown', when you are not confident - an absent edge is safe, a "
              "wrong one is not.")
    return [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _loads_lenient(content: str) -> Any:
    s = (content or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1] if len(parts) > 1 else ""
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
        s = s.strip()
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        i, j = s.find("["), s.rfind("]")
        if 0 <= i < j:
            try:
                return json.loads(s[i:j + 1])
            except (json.JSONDecodeError, ValueError):
                return None
        return None


def parse_edges(
    content: str, *, order_index: dict[str, int], window_ids: set[str],
    token_map: dict[str, str] | None = None,
) -> list[tuple[str, str, str]]:
    """PURE — parse ``[[earlier_id, later_id, relation], …]`` into ``(a, b, relation)``.

    Keeps ONLY triples where both ids are in the window, ``a`` is strictly EARLIER than ``b``
    in the global reading order, and the relation is one of ``causes`` / ``precedes``. Drops
    self-loops, backward links, ids the model invented, and — deliberately — every pair the
    model labelled ``unknown``.

    ``unknown`` IS A FIRST-CLASS ANSWER (plan T33). It is not a parse failure and not a
    fallback to ``precedes``: for a canon check **a wrong order is worse than an absent one**,
    and the sibling relation proposer was measured at only 3-of-8 defensible. Silently
    upgrading "I cannot tell" into an edge is how an uncalibrated inference becomes world state.

    Back-compat: a 2-element pair (the pre-T33 shape) reads as ``precedes`` — the WEAKER of the
    two claims. An older cached response must not be promoted into a causal assertion it never
    made.

    ``token_map`` (``{"E1": <event id>, …}``, from `event_tokens`) resolves the E-labels the
    prompt asks for back to real ids. A value that is ALREADY an event id passes through
    unchanged, so a cached pre-token response still parses — the map is a resolution step, not
    a required encoding.

    Tolerates a ``{"edges":[…]}`` / ``{"pairs":[…]}`` wrapper or a bare list."""
    obj = _loads_lenient(content)
    if isinstance(obj, dict):
        obj = obj.get("edges") or obj.get("pairs") or []
    if not isinstance(obj, list):
        return []
    out: list[tuple[str, str, str]] = []
    for pair in obj:
        if not isinstance(pair, (list, tuple)):
            continue
        if len(pair) == 2:
            a, b, rel = pair[0], pair[1], REL_PRECEDES
        elif len(pair) == 3:
            a, b, rel = pair
            rel = str(rel or "").strip().lower()
        else:
            continue
        # 'unknown', a typo, or a kind we do not model — all three mean "no edge".
        if rel not in _ORDERED_KINDS:
            continue
        # Resolve the prompt's E-labels to real ids. An id passes through unchanged.
        if token_map:
            a = token_map.get(a, a) if isinstance(a, str) else a
            b = token_map.get(b, b) if isinstance(b, str) else b
        if (isinstance(a, str) and isinstance(b, str)
                and a in window_ids and b in window_ids and a != b
                and order_index.get(a, -1) < order_index.get(b, -1)):
            out.append((a, b, rel))
    return out


def drop_cycles(
    edges: list[tuple[str, str, str]],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """PURE — return ``(acyclic, refused)``, refusing any edge that would close a cycle.

    Mirrors the ``motif_link`` cycle guard (``composition-service/app/db/migrate.py``), which
    walks the existing edges of the SAME kind and refuses an insert whose target can already
    reach its source. Per-kind for the same reason: ``causes`` and ``precedes`` are different
    assertions, and a cycle in one is not a cycle in the other.

    ── WHY THIS EXISTS WHEN THE ORDER FILTER ALREADY MAKES CYCLES IMPOSSIBLE ────────────────
    Today every edge runs strictly forward in reading order, so the graph is a DAG by
    construction and this refuses nothing. That is exactly why it is written now and tested
    against a hand-built cycle: acyclicity is currently a property of ONE filter in ONE
    function, and D0.1 makes world order a partial order that will eventually accept edges NOT
    derived from reading order (curated ``HAPPENS_BEFORE``, cross-chapter anchors). The day
    that filter is relaxed the guarantee disappears **silently** — a cyclic world order answers
    "did A happen before B" with yes in both directions, and nothing errors.
    """
    kept: list[tuple[str, str, str]] = []
    refused: list[tuple[str, str, str]] = []
    reach: dict[str, dict[str, set[str]]] = {}
    for a, b, rel in edges:
        adj = reach.setdefault(rel, {})
        # Can b already reach a? Then a -> b closes a loop.
        seen: set[str] = set()
        stack = [b]
        closes = False
        while stack:
            node = stack.pop()
            if node == a:
                closes = True
                break
            if node in seen:
                continue
            seen.add(node)
            stack.extend(adj.get(node, ()))
        if closes:
            refused.append((a, b, rel))
            continue
        adj.setdefault(a, set()).add(b)
        kept.append((a, b, rel))
    return kept, refused


def _job_content(job: Any) -> str:
    result = getattr(job, "result", None) or {}
    msgs = result.get("messages") or []
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return msgs[0].get("content", "") or ""
    return ""


async def infer_causal_edges(
    llm: Any, *, user_id: str, model_source: str, model_ref: str,
    events: list[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    """Infer `(a, b, relation)` edges over the ORDERED ``events`` (already filtered +
    event-order-sorted by the caller). Slides a window with overlap, ≤ ``_MAX_WINDOWS`` LLM
    calls. ADVISORY: NEVER raises; dedupes. Returns sorted unique triples, cycle-free.

    ``relation`` is ``causes`` or ``precedes`` (plan T33 / D0.1). Pairs the model could not
    label are dropped rather than downgraded — see ``parse_edges``."""
    if len(events) < 2:
        return []
    order_index = {e["id"]: i for i, e in enumerate(events)}
    edges: set[tuple[str, str, str]] = set()
    windows = 0
    for start in range(0, len(events), _STRIDE):
        if windows >= _MAX_WINDOWS:
            logger.warning("causal-edges: hit window cap %d — truncating", _MAX_WINDOWS)
            break
        window_ev = events[start:start + _WINDOW]
        if len(window_ev) < 2:
            break
        windows += 1
        window_ids = {e["id"] for e in window_ev}
        try:
            job = await llm.submit_and_wait(
                user_id=user_id, operation="chat", model_source=model_source,
                model_ref=model_ref,
                input={"messages": build_messages(window_ev),
                       "temperature": 0.0,
                        "max_tokens": max_tokens_for("causal_edges", target=len(window_ev)),
                       # D-T33-CORPUS-BITE-REASONING-MODEL — turn hidden thinking OFF.
                       #
                       # The corpus bite for this extractor returned `edges_written: 0` over
                       # 27 events, and the cause was not the parse path: the configured chat
                       # model is a REASONING model that spent its whole budget on
                       # `reasoning_content`. Read from `llm_jobs` at the time:
                       #   job 1  finish_reason=stop    output=1182  reasoning=1176  content="[]"
                       #   job 2  finish_reason=length  output=4950  reasoning=4947  content=""
                       # The traces were coherent and on-task — the model understood the
                       # prompt and ran out of budget before answering.
                       #
                       # `max_tokens_for("causal_edges", ...)` sizes the ANSWER, not a
                       # reasoning preamble, and this call wants strict JSON, so a preamble is
                       # pure waste here. The deferral framed the fix as a provider-config
                       # decision; it is not — this is a PER-REQUEST knob the SDK documents as
                       # the cross-provider way to disable hidden thinking, and using it
                       # manages no model lifecycle.
                       **reasoning_fields(ReasoningDirective(
                           effort="none", passthrough=False, source="non_reasoning")),
                       },
                job_meta={"extractor": "causal_edges"},
            )
        except Exception as exc:
            logger.warning("causal-edges window failed: %r", exc)
            continue
        if (why := unusable(job, "causal_edges")):
            continue
        edges.update(parse_edges(
            _job_content(job), order_index=order_index, window_ids=window_ids,
            token_map=event_tokens(window_ev)))
        if start + _WINDOW >= len(events):
            break
    # Sort BEFORE the cycle guard so the refusal is deterministic: which edge of a cycle gets
    # dropped must not depend on set iteration order, or two runs over the same corpus would
    # disagree about world order and neither would be reproducible.
    kept, refused = drop_cycles(sorted(edges))
    if refused:
        logger.warning("causal-edges: refused %d edge(s) that would close a cycle: %s",
                       len(refused), refused[:5])
    return kept
