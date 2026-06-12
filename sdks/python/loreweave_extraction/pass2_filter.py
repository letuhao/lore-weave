"""Cycle 72 — Pass2 precision filter (post-extraction precision pass).

Promotes the eval-side `_PRECISION_SYSTEM` judge (see
`services/knowledge-service/tests/quality/llm_judge.py`) to a
production filter that runs AFTER `extract_pass2` returns. Drops
items the filter LLM says are not supported by the source text;
preserves `Pass2Candidates` shape for downstream writers.

Design highlights (per docs/specs/2026-05-29-pass2-precision-filter.md):

- **Best-effort, never raises.** LLM failure → `filter_status="degraded"`
  + Pass A candidates returned unchanged. The caller's existing
  retry/persist contract is never disturbed by filter problems.
- **Immutable.** Returns a NEW `Pass2Candidates` instance via
  `dataclasses.replace`; never mutates input.
- **Three-category concurrent gather.** Entity / relation / event
  filter calls run in `asyncio.gather` per chapter — total latency is
  the slowest single category, not the sum.
- **Per-category subset.** `config.categories` lets the caller filter
  any subset; categories not in the tuple pass through unchanged with
  coverage=1.0.
- **Facts NOT filtered** in this cycle (per spec D2 — facts have no
  entity FK and their canonical form is summary-level prose; deferred
  to `D-PASS2-FILTER-FACTS-SUPPORT`).
- **Op-reuse.** Filter calls the gateway with `operation="chat"`
  (matching `llm_judge.py:400`), not a new `JobOperation` enum value.
  See `feedback_op_enum_reuse_via_chat_precedent`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Literal

from loreweave_extraction._types import LLMClientProtocol
from loreweave_extraction.extractors.precision_filter_prompts import (
    build_precision_prompt,
)
from loreweave_extraction.pass2 import FilterStatus, Pass2Candidates

logger = logging.getLogger(__name__)

__all__ = [
    "Category",
    "PartialPolicy",
    "VerdictLabel",
    "DecisionHandler",
    "PrecisionFilterConfig",
    "FilterDecision",
    "apply_precision_filter",
    "load_candidates_from_dump",
]


Category = Literal["entity", "relation", "event"]
PartialPolicy = Literal["keep", "drop", "demote"]
VerdictLabel = Literal["supported", "partial", "unsupported", "unjudged"]


@dataclass(frozen=True)
class FilterDecision:
    """One per-item filter outcome. Surfaced via the optional
    `on_decision` callback so the caller can populate Prometheus
    counters without coupling library to a metrics module."""

    category: Category
    idx: int
    verdict: VerdictLabel


DecisionHandler = Callable[[FilterDecision], None]


@dataclass(frozen=True)
class PrecisionFilterConfig:
    """Config for the Pass2 precision filter pass.

    A ``None`` filter config on `extract_pass2` disables filtering
    entirely (default). When set, all kwargs route through to the
    LLM call shape used by `llm_judge.py`'s precision pass.

    Attributes:
        model_ref: gateway model identifier (e.g. claude-4.7-opus UUID
            or alias name).
        model_source: ``"user_model"`` (BYOK) or ``"platform_model"``.
            Independent from extraction's model_source per OQ-1.
        partial_policy: how to handle judge verdict ``"partial"``.
            ``"keep"`` (default) treats as supported; ``"drop"`` treats
            as unsupported; ``"demote"`` is reserved but currently
            raises `NotImplementedError` in `__post_init__`.
        categories: subset of ``{"entity", "relation", "event"}`` to
            filter; unselected categories pass through unchanged.
        max_items_per_batch: judge-batch size. Calibrated from
            `llm_judge.py` for reasoning-token bursts on gemma-4-26b
            on LM Studio; may need empirical retune for claude-4.7-opus
            per LOW-1 fold.
        transient_retry_budget: passed through to LLM client's
            transient retry budget; matches `llm_judge.py` default 1.
    """

    model_ref: str
    model_source: Literal["user_model", "platform_model"] = "user_model"
    partial_policy: PartialPolicy = "keep"
    categories: tuple[Category, ...] = ("entity", "relation", "event")
    max_items_per_batch: int = 3
    transient_retry_budget: int = 1

    def __post_init__(self) -> None:
        if self.partial_policy == "demote":
            raise NotImplementedError(
                "partial_policy='demote' is reserved for a follow-up "
                "cycle; use 'keep' or 'drop'"
            )
        if not self.categories:
            raise ValueError(
                "PrecisionFilterConfig.categories must be non-empty "
                "(use partial_policy + skip-categories to selectively "
                "disable a category instead of an empty tuple)"
            )
        if self.max_items_per_batch < 1:
            raise ValueError(
                "max_items_per_batch must be >= 1"
            )


# ── Item formatting (Pydantic → judge-friendly line) ───────────────────


def _format_entity(it: dict[str, Any]) -> str:
    return f'{it.get("name", "")} (kind: {it.get("kind", "")})'


def _format_relation(it: dict[str, Any]) -> str:
    pol = it.get("polarity", "affirm")
    neg = " [NEGATED]" if pol == "negate" else ""
    return (
        f'{it.get("subject", "")} --{it.get("predicate", "")}--> '
        f'{it.get("object", "")}{neg}'
    )


def _format_event(it: dict[str, Any]) -> str:
    # Pass2 event candidates carry `name` + `summary` + `participants`.
    # The judge sees a one-line gist preferring summary when present
    # (matches `llm_judge.format_items_for_judge` event branch).
    summary = it.get("summary") or it.get("name", "")
    parts = ", ".join(it.get("participants", []) or [])
    return f"{summary} (participants: {parts})"


_FORMATTERS: dict[Category, Callable[[dict[str, Any]], str]] = {
    "entity": _format_entity,
    "relation": _format_relation,
    "event": _format_event,
}


def _pydantic_to_dict(item: Any) -> dict[str, Any]:
    """Adapt a Pydantic candidate model to the dict shape the formatters
    expect (round-trip via `model_dump(mode="json")`). Round-1 MED-1 fold."""
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return item
    raise TypeError(
        f"precision filter expected Pydantic model or dict, got {type(item)!r}"
    )


# ── JSON parsing (tolerant — mirrors llm_judge._extract_json_object) ───


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Parse the filter response into a dict, tolerating code fences
    and leading/trailing prose. Raises ValueError on hard failure."""
    if not raw or not raw.strip():
        raise ValueError("empty filter response")
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(
                f"no JSON object in filter response: {raw[:200]!r}"
            )
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("filter response is not a JSON object")
    return parsed


# ── Per-category filter primitives ─────────────────────────────────────


@dataclass
class _CategoryResult:
    """Outcome of filtering one category's list."""

    kept_indices: list[int]
    verdicts_by_idx: dict[int, VerdictLabel]

    @property
    def coverage(self) -> float:
        """Items the LLM returned a verdict for over total items.

        Used as: `n_judged / n_input`. 1.0 when the category had zero
        items (vacuous), as no LLM call was needed.
        """
        return 0.0  # placeholder; computed by caller (knows n_input)


def _resolve_partial(policy: PartialPolicy) -> Literal["keep", "drop"]:
    """Pre-resolve partial handling. ``"demote"`` is rejected by
    PrecisionFilterConfig.__post_init__ before this is reached."""
    if policy == "keep":
        return "keep"
    if policy == "drop":
        return "drop"
    # Defensive: should be impossible.
    raise ValueError(f"unsupported partial_policy={policy!r}")


def _apply_verdict(
    verdict: VerdictLabel,
    partial_policy: Literal["keep", "drop"],
) -> bool:
    """Map a verdict + policy to a keep/drop decision.

    ``"supported"`` → keep, ``"unsupported"`` → drop, ``"partial"`` →
    per policy, ``"unjudged"`` → per policy (LOW-1 fold: a missing
    verdict is treated identically to ``"partial"`` so the caller's
    intent on partial drives the unjudged path too).
    """
    if verdict == "supported":
        return True
    if verdict == "unsupported":
        return False
    # partial or unjudged
    return partial_policy == "keep"


async def _call_filter_llm(
    *,
    user_id: str,
    config: PrecisionFilterConfig,
    llm_client: LLMClientProtocol,
    system: str,
    user: str,
    n_items: int,
) -> str:
    """One filter chat call through the gateway. Returns the content
    string. Raises ValueError on any non-usable outcome so the per-batch
    caller's `except ValueError` marks the batch unjudged instead of
    aborting the whole filter pass (mirrors `llm_judge._call_judge`)."""
    # Conservative output budget: ~250 tokens per verdict, mirrors
    # llm_judge calibration for reasoning-token bursts. Tune in BUILD
    # if filter_coverage shows truncation pattern.
    max_tokens = 1536 + 256 * max(1, n_items)
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=config.model_source,
            model_ref=config.model_ref,
            input={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "text"},
                "temperature": 0.0,
                "max_tokens": max_tokens,
                # Anti-thinking flag for reasoning-tuned local models;
                # harmless on plain models.
                "chat_template_kwargs": {
                    "thinking": False,
                    "enable_thinking": False,
                },
            },
            chunking=None,
            job_meta={"extractor": "pass2_filter"},
            transient_retry_budget=config.transient_retry_budget,
        )
    except Exception as exc:  # noqa: BLE001 — translate to ValueError
        raise ValueError(f"filter LLM call failed: {exc}") from exc
    if getattr(job, "status", None) != "completed":
        raise ValueError(
            f"filter job ended status={getattr(job, 'status', '?')}"
        )
    result = getattr(job, "result", None) or {}
    # The gateway returns the chat-completion response as
    # `result["messages"][0]` (assistant message). Mirrors
    # `llm_judge._call_judge` so the filter and judge stay structurally
    # identical against the same gateway contract.
    content = ""
    if isinstance(result, dict):
        messages = result.get("messages") or []
        if messages and isinstance(messages[0], dict):
            content = messages[0].get("content", "") or ""
        if not content:
            # Fallback: some gateway shapes may flatten to a top-level
            # `content` string. Preserve compatibility.
            content = result.get("content", "") or ""
    if not content:
        raise ValueError("filter job returned empty content")
    return content


def _parse_verdicts(content: str, n_items: int) -> dict[int, VerdictLabel]:
    """Parse `{"verdicts":[{"idx":N,"verdict":"...","reason":"..."}]}`
    into a mapping of idx → verdict. Items the response omitted stay
    out of the dict (caller defaults them to ``"unjudged"``)."""
    parsed = _extract_json_object(content)
    verdicts = parsed.get("verdicts", [])
    if not isinstance(verdicts, list):
        raise ValueError(
            f"verdicts key is not a list: {type(verdicts).__name__}"
        )
    out: dict[int, VerdictLabel] = {}
    for entry in verdicts:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry["idx"])
        except (KeyError, TypeError, ValueError):
            continue
        v = entry.get("verdict")
        if v in ("supported", "partial", "unsupported"):
            # Only record the first occurrence per idx (defensive
            # against duplicate-idx responses from the LLM).
            if idx not in out and 0 <= idx < n_items:
                out[idx] = v  # type: ignore[assignment]
    return out


async def _filter_one_category(
    *,
    category: Category,
    items: list[Any],
    text: str,
    user_id: str,
    config: PrecisionFilterConfig,
    llm_client: LLMClientProtocol,
    on_decision: DecisionHandler | None,
) -> tuple[_CategoryResult, float, list[int]]:
    """Filter one category's item list.

    Returns:
        (result, coverage, kept_indices_in_order)
            result.verdicts_by_idx maps each input idx → verdict
            coverage = n_judged / n_input (1.0 if n_input == 0)
            kept_indices_in_order = sorted list of idx values to keep
    """
    n_input = len(items)
    if n_input == 0:
        return (
            _CategoryResult(kept_indices=[], verdicts_by_idx={}),
            1.0,
            [],
        )

    item_dicts = [_pydantic_to_dict(it) for it in items]
    formatter = _FORMATTERS[category]
    formatted_lines = [formatter(d) for d in item_dicts]

    system = build_precision_prompt(suppress_thinking=True)
    partial_resolved = _resolve_partial(config.partial_policy)

    verdicts_by_idx: dict[int, VerdictLabel] = {}
    batch_size = config.max_items_per_batch

    # Build user prompts per batch. Each batch's numbering is LOCAL
    # (0..batch_size-1); we map back to the global idx after parsing.
    for batch_start in range(0, n_input, batch_size):
        batch_end = min(batch_start + batch_size, n_input)
        batch_lines = formatted_lines[batch_start:batch_end]
        numbered = "\n".join(
            f"[{i}] {line}" for i, line in enumerate(batch_lines)
        )
        user_msg = (
            f"SOURCE TEXT:\n{text}\n\n"
            f"ITEMS (category={category}):\n{numbered}\n"
        )
        try:
            content = await _call_filter_llm(
                user_id=user_id,
                config=config,
                llm_client=llm_client,
                system=system,
                user=user_msg,
                n_items=batch_end - batch_start,
            )
            local_verdicts = _parse_verdicts(
                content, n_items=batch_end - batch_start
            )
        except ValueError as exc:
            logger.warning(
                "pass2 filter batch failed cat=%s batch=[%d,%d): %s",
                category, batch_start, batch_end, exc,
            )
            local_verdicts = {}

        # Map local idx → global idx; record verdicts.
        for local_idx, v in local_verdicts.items():
            global_idx = batch_start + local_idx
            verdicts_by_idx[global_idx] = v

    # Walk every input item to compute kept set + emit decisions.
    kept_indices: list[int] = []
    for idx in range(n_input):
        verdict: VerdictLabel = verdicts_by_idx.get(idx, "unjudged")
        if _apply_verdict(verdict, partial_resolved):
            kept_indices.append(idx)
        if on_decision is not None:
            try:
                on_decision(
                    FilterDecision(
                        category=category, idx=idx, verdict=verdict
                    )
                )
            except Exception:  # noqa: BLE001 — observability must not poison filter
                logger.exception(
                    "on_decision callback raised; continuing filter pass"
                )

    coverage = len(verdicts_by_idx) / n_input

    return (
        _CategoryResult(
            kept_indices=kept_indices, verdicts_by_idx=verdicts_by_idx
        ),
        coverage,
        kept_indices,
    )


# ── Public entry point ─────────────────────────────────────────────────


async def apply_precision_filter(
    candidates: Pass2Candidates,
    *,
    text: str,
    config: PrecisionFilterConfig,
    user_id: str,
    llm_client: LLMClientProtocol,
    on_decision: DecisionHandler | None = None,
) -> Pass2Candidates:
    """Apply the precision filter pass to existing Pass2 candidates.

    Empty input → returns candidates unchanged with
    `filter_status="skipped"`.

    Filter pass succeeds → returns NEW `Pass2Candidates` with filtered
    lists + `filter_status="applied"` + per-category coverage.

    Filter pass fails (any unexpected exception bubbles up past the
    per-batch handlers) → returns NEW `Pass2Candidates` with Pass A
    lists unchanged + `filter_status="degraded"`. Caller's pipeline
    continues as if filter never ran.

    Args:
        candidates: input candidate set (typically the output of
            `extract_pass2`). Not mutated.
        text: SOURCE TEXT used as the verdict ground truth.
        config: filter config (model + policy + categories).
        user_id: gateway user identifier for the filter LLM call.
        llm_client: shared LLM client (same protocol as extractor).
        on_decision: optional callback invoked once per item with the
            filter's verdict. Used for Prometheus / telemetry; the
            library accepts None and silently drops.

    Returns:
        A new `Pass2Candidates` instance. Never the same object as
        `candidates`.
    """
    # Vacuous case — no items anywhere.
    if candidates.is_empty():
        return replace(
            candidates,
            filter_status="skipped",
            filter_coverage={c: 1.0 for c in config.categories},
        )

    # Per-category async filter calls run concurrently. Each helper
    # returns (CategoryResult, coverage, kept_indices_in_order).
    coros: dict[Category, Awaitable[tuple[_CategoryResult, float, list[int]]]] = {}
    if "entity" in config.categories:
        coros["entity"] = _filter_one_category(
            category="entity",
            items=candidates.entities,
            text=text,
            user_id=user_id,
            config=config,
            llm_client=llm_client,
            on_decision=on_decision,
        )
    if "relation" in config.categories:
        coros["relation"] = _filter_one_category(
            category="relation",
            items=candidates.relations,
            text=text,
            user_id=user_id,
            config=config,
            llm_client=llm_client,
            on_decision=on_decision,
        )
    if "event" in config.categories:
        coros["event"] = _filter_one_category(
            category="event",
            items=candidates.events,
            text=text,
            user_id=user_id,
            config=config,
            llm_client=llm_client,
            on_decision=on_decision,
        )

    try:
        results = await asyncio.gather(*coros.values(), return_exceptions=False)
    except Exception as exc:  # noqa: BLE001 — promote to degraded
        logger.warning(
            "pass2 precision filter degraded — gather raised %s: %s",
            type(exc).__name__, exc,
        )
        return replace(
            candidates,
            filter_status="degraded",
            filter_coverage={c: 0.0 for c in config.categories},
        )

    # Stitch results back into per-category lists.
    coverage_map: dict[str, float] = {}
    new_entities = list(candidates.entities)
    new_relations = list(candidates.relations)
    new_events = list(candidates.events)
    for cat, (_, coverage, kept_indices) in zip(coros.keys(), results):
        coverage_map[cat] = coverage
        if cat == "entity":
            new_entities = [candidates.entities[i] for i in kept_indices]
        elif cat == "relation":
            new_relations = [candidates.relations[i] for i in kept_indices]
        elif cat == "event":
            new_events = [candidates.events[i] for i in kept_indices]

    # Categories the config did NOT filter → coverage = 1.0 (vacuous,
    # all items pass through unchanged).
    for c in ("entity", "relation", "event"):
        coverage_map.setdefault(c, 1.0)

    return replace(
        candidates,
        entities=new_entities,
        relations=new_relations,
        events=new_events,
        filter_status="applied",
        filter_coverage=coverage_map,
    )


# ── Dump fixture loader (HIGH-1 round-1 fold) ──────────────────────────


def load_candidates_from_dump(dump_dir: str | "PathLike[str]") -> Pass2Candidates:
    """Reconstruct `Pass2Candidates` from a saved `actual.json` dump.

    Layout (per `tests/quality/test_extraction_eval.py` dump format):

        <dump_dir>/
          actual.json   <-- {"entities": [...], "relations": [...], "events": [...], "facts": [...]}

    Used by the cycle-72 eval validation harness to load a saved
    c70a Pass A baseline and feed it into the filter, eliminating
    extraction nondeterminism from the A/B comparison (per spec
    HIGH-1 round-1 fold).

    Returns:
        Pass2Candidates with `filter_status="skipped"` (unfiltered raw
        Pass A snapshot). Caller invokes `apply_precision_filter` on
        the returned candidates to produce the filtered variant.
    """
    from pathlib import Path

    # Lazy imports to avoid pulling Pydantic candidates at module load.
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    from loreweave_extraction.extractors.event import LLMEventCandidate
    from loreweave_extraction.extractors.fact import LLMFactCandidate
    from loreweave_extraction.extractors.relation import LLMRelationCandidate

    path = Path(dump_dir) / "actual.json"
    raw = path.read_text(encoding="utf-8")
    blob = json.loads(raw)

    # Eval dumps are a minimal projection — full Pydantic candidates
    # have more required fields (aliases, confidence, canonical_*).
    # Use `model_construct` to skip validation + supply safe defaults
    # so downstream `.model_dump()` works without ValidationError.

    def _entity(i: int, e: dict) -> LLMEntityCandidate:
        name = e.get("name", "")
        return LLMEntityCandidate.model_construct(
            name=name,
            kind=e.get("kind", ""),
            aliases=list(e.get("aliases", []) or []),
            confidence=float(e.get("confidence", 1.0)),
            canonical_name=e.get("canonical_name") or name.lower(),
            canonical_id=e.get("canonical_id") or f"eid-loaded-{i}",
        )

    def _relation(i: int, r: dict) -> LLMRelationCandidate:
        return LLMRelationCandidate.model_construct(
            subject=r.get("subject", ""),
            predicate=r.get("predicate", ""),
            object=r.get("object", ""),
            polarity=r.get("polarity", "affirm"),
            modality=r.get("modality", "actual"),
            confidence=float(r.get("confidence", 1.0)),
            subject_id=r.get("subject_id"),
            object_id=r.get("object_id"),
            relation_id=r.get("relation_id") or f"rid-loaded-{i}",
        )

    def _event(i: int, ev: dict) -> LLMEventCandidate:
        participants = list(ev.get("participants", []) or [])
        return LLMEventCandidate.model_construct(
            name=ev.get("name") or ev.get("summary", "")[:40],
            kind=ev.get("kind", "action"),
            participants=participants,
            participant_ids=list(ev.get("participant_ids", [])
                or [None] * len(participants)),
            location=ev.get("location"),
            time_cue=ev.get("time_cue"),
            event_date=ev.get("event_date"),
            summary=ev.get("summary", ""),
            confidence=float(ev.get("confidence", 1.0)),
            event_id=ev.get("event_id") or f"evid-loaded-{i}",
        )

    def _fact(i: int, f: dict) -> LLMFactCandidate:
        return LLMFactCandidate.model_construct(
            content=f.get("content", ""),
            type=f.get("type", "trait"),
            subject=f.get("subject"),
            polarity=f.get("polarity", "affirm"),
            modality=f.get("modality", "actual"),
            confidence=float(f.get("confidence", 1.0)),
            fact_id=f.get("fact_id") or f"fid-loaded-{i}",
        )

    return Pass2Candidates(
        entities=[_entity(i, e) for i, e in enumerate(blob.get("entities", []))],
        relations=[_relation(i, r) for i, r in enumerate(blob.get("relations", []))],
        events=[_event(i, ev) for i, ev in enumerate(blob.get("events", []))],
        facts=[_fact(i, f) for i, f in enumerate(blob.get("facts", []))],
    )
