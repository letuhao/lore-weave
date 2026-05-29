"""LLM-as-judge eval for extraction quality (R&D track).

**Why this exists.** The rule-based scorer in [eval_harness.py](./eval_harness.py)
matches extractions to a hand-annotated gold set by *exact string / token
equality* (entities), *exact triple + an 8-entry synonym map* (relations),
and *bag-of-words token overlap* (events). Extraction is an interpretive
task — many surface forms express the same content — so that scorer
measures *agreement with one conservative annotation philosophy*, not
extraction correctness. The `fp_annotation_gap` / `precision_lenient`
patches already in the harness are an implicit admission of that bias.

This judge instead reads the **source chapter text** and asks a strong
LLM whether each extraction is *actually supported by the text* (precision)
and whether each gold item is *captured under any phrasing* (recall). That
escapes the conservative-gold bias for precision and the synonym/paraphrase
bias for both.

**Conventions (same as every other service surface).**
- Every LLM call goes through the shared `LLMClient` →
  `loreweave_llm` SDK → provider-registry gateway. NO direct provider
  SDK calls (gateway invariant).
- The judge model is configurable and **MUST differ from the extraction
  model** — a model judging its own output self-reinforces. Pass a
  gemma model_ref when extraction ran on Qwen, etc.

**Decoupled from extraction.** This judges already-produced extraction
output (the dump `actual.json`) against the fixture source — it does NOT
re-run extraction. So the judge model can be loaded alone (24 GB VRAM
can't hold the extraction model + judge model at once).

**Honest limits.** LLM judges are weakest on relation extraction
(literature reports judge accuracy often <50% there) and on the weak
multilingual axis (a judge that is itself weak in Chinese can't catch a
Chinese extraction error). Treat local-judge numbers as a *relative*
signal across tuning cycles, and run a cloud-judge calibration pass on a
sample before trusting absolute values.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.clients.llm_client import LLMClient
from loreweave_extraction import NO_THINK_PREFIX, build_precision_prompt
from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError

logger = logging.getLogger(__name__)

# Cycle 72 — _NO_THINK_PREFIX is now sourced from the SDK so the
# precision filter (production) and the precision judge (eval-side)
# stay byte-identical. Keep the alias for `_RECALL_SYSTEM` below.
_NO_THINK_PREFIX = NO_THINK_PREFIX

__all__ = [
    "ItemVerdict",
    "GoldVerdict",
    "CategoryJudgement",
    "ChapterJudgement",
    "judge_precision",
    "judge_recall",
    "judge_category",
    "judge_chapter",
    "format_items_for_judge",
    "run_dump_judge",
]


Category = Literal["entity", "relation", "event"]

# Per-item output token budget for the judge response. Each verdict is
# {"idx":N,"verdict":"...","reason":"..."} — the reason is capped at ~15
# words by the prompt, so ~60 tokens/item is generous. The floor covers
# the JSON envelope for a zero-item category (shouldn't be called, but
# safe).
#
# The budget is deliberately roomy because a *reasoning* judge model
# (qwen-thinking, deepseek-r1, etc.) spends `reasoning_tokens` from the
# same max_tokens pool BEFORE emitting any content — a tight budget
# leaves zero room for the JSON and the response comes back empty.
#
# Session-67 cont.5 calibration: even nominally non-reasoning gemma-4-26b
# variants on LM Studio emit massive reasoning_tokens (observed ~1000
# tokens per judge call, finish_reason=length on 67% of jobs). RAGAS /
# DeepEval / TruLens sidestep this by per-item structured-output calls;
# we keep batching but bump the budget 3× (per-item 96→256) + base
# 512→1536 to leave ~2000 tokens for content even after reasoning burns
# ~1000. Also lower default batch_size 8→3 so each call's content need
# stays small (verdicts × 60 tokens). Override via env.
_BASE_OUTPUT_TOKENS = int(os.environ.get("KNOWLEDGE_JUDGE_BASE_TOKENS", "1536"))
_PER_ITEM_OUTPUT_TOKENS = int(os.environ.get("KNOWLEDGE_JUDGE_PER_ITEM_TOKENS", "256"))

# Max items judged per LLM call. A judge asked to return 30+ verdicts in
# one JSON object truncates or drops items (observed: speckled_band's 30
# entities came back wholly unjudged). Small batches keep each response
# short enough to enumerate reliably; the per-batch idx is mapped back to
# the global item index by the caller. Trades call count for coverage.
#
# Calibrated down 8→3 (session-67 cont.5) because reasoning-heavy local
# judges (gemma-4-26b on LM Studio) eat the per-call token budget; small
# batches cap the worst-case content need per response.
_JUDGE_BATCH_SIZE = int(os.environ.get("KNOWLEDGE_JUDGE_BATCH_SIZE", "3"))


# ── Verdict / result types ──────────────────────────────────────────


@dataclass
class ItemVerdict:
    """One precision verdict — is extracted item `idx` supported by the text?"""

    idx: int
    verdict: Literal["supported", "partial", "unsupported", "unjudged"]
    reason: str

    @property
    def credit(self) -> float:
        """Precision credit: supported=1.0, partial=0.5, else 0.0."""
        if self.verdict == "supported":
            return 1.0
        if self.verdict == "partial":
            return 0.5
        return 0.0


@dataclass
class GoldVerdict:
    """One recall verdict — is gold item `gold_idx` captured by the extraction?

    `judged=False` marks a gold item the judge omitted from its response
    (not the same as "not found" — we simply have no verdict). Omitted
    items are EXCLUDED from the recall denominator, not counted as misses,
    so a flaky judge depresses *coverage* rather than faking a low recall.
    """

    gold_idx: int
    found: bool
    matched_actual_idx: int | None
    reason: str
    judged: bool = True


@dataclass
class CategoryJudgement:
    """Judge result for one category (entity / relation / event) of one chapter."""

    category: Category
    n_extracted: int
    n_gold: int
    precision_verdicts: list[ItemVerdict] = field(default_factory=list)
    recall_verdicts: list[GoldVerdict] = field(default_factory=list)

    @property
    def n_unjudged(self) -> int:
        return sum(1 for v in self.precision_verdicts if v.verdict == "unjudged")

    @property
    def n_precision_judged(self) -> int:
        return sum(1 for v in self.precision_verdicts if v.verdict != "unjudged")

    @property
    def n_recall_judged(self) -> int:
        return sum(1 for v in self.recall_verdicts if v.judged)

    @property
    def precision_coverage(self) -> float:
        """Fraction of extracted items the judge actually returned a
        verdict for. Low coverage = distrust the precision number."""
        if self.n_extracted == 0:
            return 1.0
        return self.n_precision_judged / self.n_extracted

    @property
    def recall_coverage(self) -> float:
        if self.n_gold == 0:
            return 1.0
        return self.n_recall_judged / self.n_gold

    @property
    def precision(self) -> float | None:
        """Credit over the items the judge ACTUALLY judged (unjudged items
        excluded from the denominator — an omitted verdict is missing data,
        not a false positive). 1.0 when nothing was extracted (vacuously
        precise). None when items were extracted but none could be judged
        (the number would be meaningless)."""
        if self.n_extracted == 0:
            return 1.0
        if self.n_precision_judged == 0:
            return None
        return sum(v.credit for v in self.precision_verdicts) / self.n_precision_judged

    @property
    def recall(self) -> float | None:
        """Found / judged-gold. 1.0 when there is no gold to find. None
        when gold exists but none of it could be judged."""
        if self.n_gold == 0:
            return 1.0
        if self.n_recall_judged == 0:
            return None
        return (
            sum(1 for v in self.recall_verdicts if v.found and v.judged)
            / self.n_recall_judged
        )


@dataclass
class ChapterJudgement:
    """Aggregate judge result across the three categories of one chapter."""

    chapter: str
    entity: CategoryJudgement
    relation: CategoryJudgement
    event: CategoryJudgement

    @property
    def categories(self) -> list[CategoryJudgement]:
        return [self.entity, self.relation, self.event]

    @property
    def precision(self) -> float | None:
        """Item-weighted precision across all categories, over JUDGED items
        only (a chapter with many entities and few events weights entities
        more — matches the rule-based harness's unified-item philosophy).
        None when items were extracted but none could be judged."""
        total_extracted = sum(c.n_extracted for c in self.categories)
        if total_extracted == 0:
            return 1.0
        judged = sum(c.n_precision_judged for c in self.categories)
        if judged == 0:
            return None
        credit = sum(
            v.credit for c in self.categories for v in c.precision_verdicts
        )
        return credit / judged

    @property
    def recall(self) -> float | None:
        total_gold = sum(c.n_gold for c in self.categories)
        if total_gold == 0:
            return 1.0
        judged = sum(c.n_recall_judged for c in self.categories)
        if judged == 0:
            return None
        found = sum(
            1 for c in self.categories
            for v in c.recall_verdicts if v.found and v.judged
        )
        return found / judged

    @property
    def precision_coverage(self) -> float:
        total = sum(c.n_extracted for c in self.categories)
        if total == 0:
            return 1.0
        return sum(c.n_precision_judged for c in self.categories) / total

    @property
    def recall_coverage(self) -> float:
        total = sum(c.n_gold for c in self.categories)
        if total == 0:
            return 1.0
        return sum(c.n_recall_judged for c in self.categories) / total


# ── Prompt construction ─────────────────────────────────────────────


# Session-67 cont.5: explicit anti-thinking instruction added — local
# reasoning-capable judges (gemma-4-26b on LM Studio observed burning
# ~1000 reasoning_tokens per call, finishing 67% with finish_reason=length
# and truncated JSON). Pattern borrowed from RAGAS/DeepEval which use
# structured output for the same reason; we keep prompt-only JSON since
# the gateway doesn't yet wire tool-use for the judge path.
#
# Cycle 72: _PRECISION_SYSTEM is now SDK-sourced — see
# loreweave_extraction.extractors.precision_filter_prompts. The
# production precision filter (sdks/python/loreweave_extraction/
# pass2_filter.py) and this eval-side judge MUST stay byte-identical
# or filter F1 will not match judge F1.
_PRECISION_SYSTEM = build_precision_prompt(suppress_thinking=True)

_RECALL_SYSTEM = _NO_THINK_PREFIX + (
    "You are a meticulous literary-extraction auditor. You are given the "
    "SOURCE TEXT of one chapter, a REFERENCE list of items that should be "
    "extractable from it, and the list of items a system ACTUALLY "
    "extracted. For EACH reference item, decide whether the extraction "
    "captured it under ANY phrasing or equivalent form.\n\n"
    "Judge by MEANING, not surface wording. The text may be English, "
    "Chinese, or Vietnamese; judge it in its own language and script.\n\n"
    "Reply with ONLY a JSON object, no prose or markdown fences:\n"
    '{"verdicts":[{"gold_idx":<int>,"found":<true|false>,'
    '"matched":<int|null>,"reason":"<=15 words"}]}\n'
    '"matched" is the idx of the actual item that captures the reference '
    "item, or null when found is false. Return one verdict per reference "
    "item, preserving gold_idx."
)


def format_items_for_judge(category: Category, items: list[Any]) -> list[str]:
    """Render extraction items into one human-readable line each.

    `items` shapes (matching the dump `actual.json` / `expected.json`):
      - entity:   {"name","kind",...}
      - relation: {"subject","predicate","object","polarity"?} or
                  {"subject","predicate","object"}
      - event:    {"summary","participants":[...]}
    """
    lines: list[str] = []
    for it in items:
        if category == "entity":
            lines.append(f'{it.get("name", "")} (kind: {it.get("kind", "")})')
        elif category == "relation":
            pol = it.get("polarity", "affirm")
            neg = " [NEGATED]" if pol == "negate" else ""
            lines.append(
                f'{it.get("subject", "")} --{it.get("predicate", "")}--> '
                f'{it.get("object", "")}{neg}'
            )
        else:  # event
            parts = ", ".join(it.get("participants", []) or [])
            lines.append(f'{it.get("summary", "")} (participants: {parts})')
    return lines


def _numbered(lines: list[str]) -> str:
    return "\n".join(f"[{i}] {line}" for i, line in enumerate(lines))


def _output_tokens(n_items: int) -> int:
    return _BASE_OUTPUT_TOKENS + _PER_ITEM_OUTPUT_TOKENS * max(1, n_items)


# ── JSON extraction (tolerant) ──────────────────────────────────────


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Parse the judge response into a dict, tolerating code fences and
    leading/trailing prose. Raises ValueError on hard failure."""
    if not raw or not raw.strip():
        raise ValueError("empty judge response")
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ``` fences.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the first balanced {...} span.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"no JSON object in judge response: {raw[:200]!r}")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("judge response is not a JSON object")
    return parsed


# ── LLM call ────────────────────────────────────────────────────────


async def _call_judge(
    client: LLMClient,
    *,
    judge_model: str,
    user_id: str,
    model_source: str,
    system: str,
    user: str,
    n_items: int,
) -> str:
    """One judge chat call through the gateway. Returns the content
    string. Raises ValueError on any non-usable outcome (non-completed
    job OR a gateway/transient LLM error) so the per-batch caller's
    `except ValueError` marks the batch unjudged instead of aborting the
    whole run — a single LM Studio hiccup must not kill a multi-chapter
    judge pass (MED#1, /review-impl)."""
    max_tokens = _output_tokens(n_items)
    try:
        job = await client.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=model_source,  # type: ignore[arg-type]
            model_ref=judge_model,
            input={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "text"},
                "temperature": 0.0,
                "max_tokens": max_tokens,
                # Session-67 cont.5 — try to suppress reasoning mode for
                # thinking-capable models (Qwen3-thinking, gemma variants
                # finetuned with thinking). LM Studio passes through to
                # llama.cpp; harmless when the model doesn't expose the
                # flag. Mirrors the `chat_template_kwargs` pattern from
                # the Qwen3 / DeepSeek-R1 LM Studio docs.
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            chunking=None,
            job_meta={"extractor": "llm_judge"},
            transient_retry_budget=1,
        )
    except (LLMError, LLMTransientRetryNeededError) as exc:
        raise ValueError(f"judge LLM call failed: {exc}") from exc
    if job.status != "completed":
        raise ValueError(f"judge job ended status={job.status}")
    result = job.result or {}
    # Surface the reasoning-token + finish_reason signal when content
    # truncation looks likely — helps the eval reader diagnose budget
    # shortages without re-querying llm_jobs by hand.
    usage = result.get("usage") or {}
    finish_reason = result.get("finish_reason")
    reasoning_tokens = int(usage.get("reasoning_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    # Two truncation modes:
    #   1. finish_reason="length" → hard cap, JSON definitely cut
    #   2. reasoning ate >100 tokens AND content space tight (<100 tokens
    #      remaining) → likely truncated even with finish=stop (rare)
    # Don't warn when reasoning=1 and finish=stop — that's the anti-think
    # prompt working as designed; small content is fine for small batches.
    if finish_reason == "length" or (
        reasoning_tokens > 100 and output_tokens - reasoning_tokens < 100
    ):
        logger.warning(
            "judge call near/over budget: max_tokens=%d output=%d "
            "reasoning=%d (%d%%) finish=%s — JSON likely truncated; "
            "consider raising KNOWLEDGE_JUDGE_BASE_TOKENS / "
            "KNOWLEDGE_JUDGE_PER_ITEM_TOKENS or lowering "
            "KNOWLEDGE_JUDGE_BATCH_SIZE",
            max_tokens, output_tokens, reasoning_tokens,
            int(reasoning_tokens / output_tokens * 100) if output_tokens else 0,
            finish_reason,
        )
    messages = result.get("messages") or []
    if messages and isinstance(messages[0], dict):
        return messages[0].get("content", "") or ""
    return ""


# ── Per-category judging ────────────────────────────────────────────


async def judge_precision(
    client: LLMClient,
    *,
    judge_model: str,
    user_id: str,
    model_source: str,
    source_text: str,
    category: Category,
    extracted: list[Any],
    batch_size: int = _JUDGE_BATCH_SIZE,
) -> list[ItemVerdict]:
    """Judge each extracted item against the source, in batches of
    `batch_size` (a judge asked for too many verdicts at once drops them).
    Items the judge omits are filled as `unjudged` — excluded from the
    precision denominator, surfaced via `n_unjudged` / coverage."""
    if not extracted:
        return []
    verdicts: list[ItemVerdict] = []
    for start in range(0, len(extracted), batch_size):
        batch = extracted[start : start + batch_size]
        lines = format_items_for_judge(category, batch)
        user = (
            f"SOURCE TEXT:\n{source_text}\n\n"
            f"EXTRACTED {category.upper()} ITEMS:\n{_numbered(lines)}\n\n"
            f"Judge each item. Return one verdict per item "
            f"(idx 0..{len(lines) - 1})."
        )
        try:
            raw = await _call_judge(
                client, judge_model=judge_model, user_id=user_id,
                model_source=model_source, system=_PRECISION_SYSTEM, user=user,
                n_items=len(batch),
            )
            parsed = _extract_json_object(raw)
            by_idx = _index_verdicts(parsed.get("verdicts", []), key="idx")
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "judge_precision parse/call failed category=%s batch@%d: %s "
                "— batch unjudged", category, start, exc,
            )
            by_idx = {}

        for local_i in range(len(batch)):
            global_i = start + local_i
            v = by_idx.get(local_i)
            if v is None:
                verdicts.append(
                    ItemVerdict(global_i, "unjudged", "judge omitted this item")
                )
                continue
            verdict = str(v.get("verdict", "")).lower().strip()
            if verdict not in ("supported", "partial", "unsupported"):
                verdict = "unjudged"
            verdicts.append(
                ItemVerdict(global_i, verdict, str(v.get("reason", ""))[:200])  # type: ignore[arg-type]
            )
    return verdicts


async def judge_recall(
    client: LLMClient,
    *,
    judge_model: str,
    user_id: str,
    model_source: str,
    source_text: str,
    category: Category,
    gold: list[Any],
    extracted: list[Any],
    batch_size: int = _JUDGE_BATCH_SIZE,
) -> list[GoldVerdict]:
    """Judge whether each gold item is captured by the extraction, in
    batches of `batch_size` gold items (the full extracted list is shown
    as the match reference in every batch)."""
    if not gold:
        return []
    # The full extracted list is the reference each batch matches against,
    # numbered globally so a returned `matched` idx is meaningful.
    actual_lines = format_items_for_judge(category, extracted)
    actual_block = _numbered(actual_lines) if actual_lines else "(none extracted)"

    verdicts: list[GoldVerdict] = []
    for start in range(0, len(gold), batch_size):
        gold_batch = gold[start : start + batch_size]
        gold_lines = format_items_for_judge(category, gold_batch)
        user = (
            f"SOURCE TEXT:\n{source_text}\n\n"
            f"REFERENCE {category.upper()} ITEMS (gold):\n{_numbered(gold_lines)}\n\n"
            f"ACTUALLY EXTRACTED {category.upper()} ITEMS:\n{actual_block}\n\n"
            f"For each reference item (gold_idx 0..{len(gold_lines) - 1}), is "
            "it captured by the extraction under any phrasing?"
        )
        try:
            raw = await _call_judge(
                client, judge_model=judge_model, user_id=user_id,
                model_source=model_source, system=_RECALL_SYSTEM, user=user,
                n_items=len(gold_batch),
            )
            parsed = _extract_json_object(raw)
            by_idx = _index_verdicts(parsed.get("verdicts", []), key="gold_idx")
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "judge_recall parse/call failed category=%s batch@%d: %s "
                "— batch unjudged", category, start, exc,
            )
            by_idx = {}

        for local_i in range(len(gold_batch)):
            global_i = start + local_i
            v = by_idx.get(local_i)
            if v is None:
                verdicts.append(
                    GoldVerdict(global_i, False, None, "judge omitted", judged=False)
                )
                continue
            matched = v.get("matched")
            matched_idx = matched if isinstance(matched, int) else None
            verdicts.append(
                GoldVerdict(
                    global_i, bool(v.get("found", False)), matched_idx,
                    str(v.get("reason", ""))[:200], judged=True,
                )
            )
    return verdicts


def _index_verdicts(verdicts: Any, *, key: str) -> dict[int, dict]:
    """Map a list of verdict dicts by their integer `key` field. Skips
    malformed entries (non-dict, missing/non-int key)."""
    out: dict[int, dict] = {}
    if not isinstance(verdicts, list):
        return out
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        idx = v.get(key)
        if isinstance(idx, bool) or not isinstance(idx, int):
            continue
        out[idx] = v
    return out


async def judge_category(
    client: LLMClient,
    *,
    judge_model: str,
    user_id: str,
    model_source: str,
    source_text: str,
    category: Category,
    extracted: list[Any],
    gold: list[Any],
) -> CategoryJudgement:
    """Run precision + recall judging for one category."""
    precision_verdicts = await judge_precision(
        client, judge_model=judge_model, user_id=user_id,
        model_source=model_source, source_text=source_text,
        category=category, extracted=extracted,
    )
    recall_verdicts = await judge_recall(
        client, judge_model=judge_model, user_id=user_id,
        model_source=model_source, source_text=source_text,
        category=category, gold=gold, extracted=extracted,
    )
    return CategoryJudgement(
        category=category,
        n_extracted=len(extracted),
        n_gold=len(gold),
        precision_verdicts=precision_verdicts,
        recall_verdicts=recall_verdicts,
    )


async def judge_chapter(
    client: LLMClient,
    *,
    judge_model: str,
    user_id: str,
    model_source: str,
    chapter: str,
    source_text: str,
    actual: dict[str, list],
    expected: dict[str, list],
) -> ChapterJudgement:
    """Judge a whole chapter's extraction (entities + relations + events).

    `actual` / `expected` are the dump shapes: each carries `entities`,
    `relations`, `events` lists of dicts.
    """
    ent = await judge_category(
        client, judge_model=judge_model, user_id=user_id,
        model_source=model_source, source_text=source_text, category="entity",
        extracted=actual.get("entities", []), gold=expected.get("entities", []),
    )
    rel = await judge_category(
        client, judge_model=judge_model, user_id=user_id,
        model_source=model_source, source_text=source_text, category="relation",
        extracted=actual.get("relations", []), gold=expected.get("relations", []),
    )
    evt = await judge_category(
        client, judge_model=judge_model, user_id=user_id,
        model_source=model_source, source_text=source_text, category="event",
        extracted=actual.get("events", []), gold=expected.get("events", []),
    )
    return ChapterJudgement(chapter=chapter, entity=ent, relation=rel, event=evt)


# ── Multi-judge ensemble adapter (cycle 2026-05-27 — spec D4) ─────────


async def run_dump_judge(
    client: LLMClient,
    *,
    judge_model_uuid: str,
    judge_label: str,
    user_id: str,
    model_source: str,
    dump_root: "Path",  # noqa: F821 — typed via TYPE_CHECKING import below
    source_text_loader,  # callable: (chapter_name) -> str | None
) -> "JudgeRunResult":  # noqa: F821
    """Run ONE judge over a whole extraction-dump tree + collect verdicts.

    The ensemble runner in `judge_ensemble.run_ensemble_judges` calls this
    (via a closure) once per judge in sequence. JIT model swaps happen at
    the LM Studio side when `judge_model_uuid` differs between calls.

    Returns a `JudgeRunResult` with status `complete` / `incomplete` /
    `failed` per spec D11:
      - complete: every chapter in dump_root produced verdicts
      - incomplete: some chapters failed mid-run but others succeeded
      - failed: raised before any chapter processed (handled by ensemble
        runner; this function does NOT catch — let exception propagate so
        the runner marks `failed` with the failure reason)
    """

    from pathlib import Path  # local import; module-level Path TYPE_CHECKING'd below
    import json as _json

    # Import judge_ensemble via a path that resolves in both environments:
    # - inside the knowledge-service container: PYTHONPATH=/app exposes
    #   `tests.quality.judge_ensemble`
    # - unit-tested from sdks/python with `quality` package on path:
    #   `quality.judge_ensemble`
    try:
        from tests.quality.judge_ensemble import (
            JudgeRunResult,
            chapter_judgement_to_verdicts,
        )
    except ModuleNotFoundError:
        from quality.judge_ensemble import (  # type: ignore[no-redef]
            JudgeRunResult,
            chapter_judgement_to_verdicts,
        )

    chapter_dirs = sorted(
        p for p in dump_root.iterdir()
        if p.is_dir() and (p / "actual.json").is_file()
    )

    verdicts: list = []
    chapters_complete: list[str] = []
    chapters_incomplete: list[str] = []

    for ch_dir in chapter_dirs:
        chapter = ch_dir.name
        try:
            actual = _json.loads((ch_dir / "actual.json").read_text(encoding="utf-8"))
            expected_path = ch_dir / "expected.json"
            expected = (
                _json.loads(expected_path.read_text(encoding="utf-8"))
                if expected_path.is_file()
                else {"entities": [], "relations": [], "events": []}
            )
            source_text = source_text_loader(chapter)
            if source_text is None:
                logger.warning(
                    "run_dump_judge: no source text for %s — skipping (judge=%s)",
                    chapter, judge_label,
                )
                chapters_incomplete.append(chapter)
                continue

            judgement = await judge_chapter(
                client,
                judge_model=judge_model_uuid,
                user_id=user_id,
                model_source=model_source,
                chapter=chapter,
                source_text=source_text,
                actual=actual,
                expected=expected,
            )
            verdicts.extend(chapter_judgement_to_verdicts(judgement))
            chapters_complete.append(chapter)
        except Exception as e:  # noqa: BLE001 — surface as `incomplete`, not `failed`
            logger.warning(
                "run_dump_judge: chapter %s failed for judge %s: %s",
                chapter, judge_label, e,
            )
            chapters_incomplete.append(chapter)

    if chapters_incomplete and not chapters_complete:
        # Every chapter failed for this judge — treat as failed dimension
        status = "failed"
        reason = f"all chapters failed; first incomplete: {chapters_incomplete[0]}"
    elif chapters_incomplete:
        status = "incomplete"
        reason = f"chapters incomplete: {chapters_incomplete}"
    else:
        status = "complete"
        reason = ""

    return JudgeRunResult(
        judge_uuid=judge_model_uuid,
        judge_label=judge_label,
        judge_status=status,  # type: ignore[arg-type]
        failure_reason=reason,
        chapters_complete=chapters_complete,
        chapters_incomplete=chapters_incomplete,
        verdicts=verdicts,
    )
