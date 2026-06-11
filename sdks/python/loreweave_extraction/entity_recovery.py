"""Cycle 73d — entity recovery (3-tier: glossary → hints → LLM classifier).

Closes the writer-cascade gap identified in cycle 73c
(eval_runs/c73c_cascade_analysis.md): relations with subject/object
names not in the entity name set get cascade-skipped at write time,
dropping ~10% of judge-supported relations even with no filter applied.

Recovery runs BEFORE the precision filter when both are enabled on
`extract_pass2`. The 3-tier resolution promotes "real" entities the
extractor missed (e.g. 仙卿, cha Tấm) and drops relations with
abstract subjects (e.g. civil practice, home peace and comfort).

Tier 1 (Glossary) + Tier 2 (Author hints) are merged into a single
caller-supplied `known_entity_kinds` map for zero-cost lookup. Tier 3
(LLM classifier) handles remaining unmatched names. Filter LLM
re-uses the same `operation="chat"` gateway path per memory
`op-enum-reuse-via-chat-precedent`.

Per cycle 73d self-review:
- Case-insensitive lookup (MED-1)
- Drop ALL relations referencing an abstract-verdict name (MED-2)
- Kind taxonomy default to "concept" for unknown verdicts (LOW-1)
- Empty unmatched short-circuit (LOW-2)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal, Mapping

from loreweave_extraction._types import LLMClientProtocol
from loreweave_extraction.canonical import entity_canonical_id
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.pass2 import Pass2Candidates

logger = logging.getLogger(__name__)

__all__ = [
    "RecoverySource",
    "VerdictLabel",
    "RecoveryDecision",
    "RecoveryDecisionHandler",
    "EntityRecoveryConfig",
    "recover_missing_entities",
]


RecoverySource = Literal["glossary", "hints", "llm", "unmatched"]
VerdictLabel = Literal["entity", "abstract", "unjudged"]

# Closed kind taxonomy mirrors LLMEntityCandidate.kind values used
# downstream by pass2_writer + Neo4j schema. Unknown verdicts default
# to "concept" (LOW-1 fold).
_KIND_TAXONOMY = ("person", "place", "organization", "artifact", "concept")
_DEFAULT_KIND = "concept"


@dataclass(frozen=True)
class RecoveryDecision:
    """One per-name recovery outcome — surfaced via on_decision callback."""

    name: str
    verdict: VerdictLabel
    source: RecoverySource
    kind: str | None = None  # set when verdict=entity (which kind it became)


RecoveryDecisionHandler = Callable[[RecoveryDecision], None]


@dataclass(frozen=True)
class EntityRecoveryConfig:
    """Config for entity recovery pass.

    Attributes:
        model_ref: gateway model_ref for Tier 3 LLM classifier
            (typically claude-4.7-opus UUID, same as precision filter).
        model_source: "user_model" or "platform_model".
        max_items_per_batch: how many unmatched names to bundle into a
            single classifier call (default 5; small enough to keep
            responses reliable, large enough to amortize call overhead).
        transient_retry_budget: passed through to LLM client.
        known_entity_kinds: Tier 1+2 name→kind lookup. Caller merges
            glossary anchors + author hints. Case-INSENSITIVE on
            lookup; original case preserved on promotion.
    """

    model_ref: str
    model_source: Literal["user_model", "platform_model"] = "user_model"
    max_items_per_batch: int = 5
    transient_retry_budget: int = 1
    known_entity_kinds: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_items_per_batch < 1:
            raise ValueError("max_items_per_batch must be >= 1")


# ── Prompt + parsing ───────────────────────────────────────────────────


_NO_THINK_PREFIX = (
    "RESPOND DIRECTLY. Do NOT think aloud, do NOT use <think> tags, do "
    "NOT write reasoning. Emit ONLY the JSON object below — no prose "
    "before or after, no markdown fences.\n\n"
)

_CLASSIFIER_SYSTEM = _NO_THINK_PREFIX + (
    "You classify whether names are PROPER ENTITIES or ABSTRACT phrases.\n\n"
    "PROPER ENTITY = a thing with a clear, specific referent. Examples:\n"
    "  - person:        Sherlock Holmes, 仙卿, cha Tấm, Mary Stoner\n"
    "  - place:         221B Baker Street, north of England, 大海, cung\n"
    "  - organization:  Scotland Yard, Bengal Artillery\n"
    "  - artifact:      iron key, watch, Eley's revolver\n"
    "  - concept:       feminism, alchemy, 道 (a named tradition / idea with"
    " referent)\n\n"
    "ABSTRACT phrase = an action description, generic category, or noun"
    " cluster that doesn't refer to a specific thing. Examples:\n"
    "  - civil practice, home peace and comfort, fancy words and refined"
    " speech, boy's games and work and manners, the reason for not having"
    " presents\n\n"
    "Judge by MEANING + the SOURCE TEXT context. The text may be in"
    " English, Chinese, or Vietnamese.\n\n"
    "For each name, return a verdict:\n"
    '  - verdict="entity" with kind="person|place|organization|artifact|concept"\n'
    '  - verdict="abstract" (kind is ignored)\n\n'
    "Reply with ONLY a JSON object, no prose or markdown fences:\n"
    '{"decisions":[{"idx":<int>,"verdict":"entity|abstract",'
    '"kind":"person|place|organization|artifact|concept",'
    '"reason":"<=15 words"}]}\n'
    "Return exactly one decision per input name, preserving idx."
)


def _extract_json_object(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        raise ValueError("empty classifier response")
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
                f"no JSON object in classifier response: {raw[:200]!r}"
            )
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("classifier response is not a JSON object")
    return parsed


def _parse_decisions(content: str) -> dict[int, tuple[VerdictLabel, str]]:
    """Return {idx: (verdict, kind)}; kind defaults to _DEFAULT_KIND for
    unknown values per LOW-1 fold."""
    parsed = _extract_json_object(content)
    decisions = parsed.get("decisions", [])
    if not isinstance(decisions, list):
        raise ValueError(
            f"decisions key not a list: {type(decisions).__name__}"
        )
    out: dict[int, tuple[VerdictLabel, str]] = {}
    for entry in decisions:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry["idx"])
        except (KeyError, TypeError, ValueError):
            continue
        verdict_raw = entry.get("verdict")
        if verdict_raw not in ("entity", "abstract"):
            continue
        kind_raw = entry.get("kind", _DEFAULT_KIND) or _DEFAULT_KIND
        kind = kind_raw if kind_raw in _KIND_TAXONOMY else _DEFAULT_KIND
        if idx not in out:
            out[idx] = (verdict_raw, kind)  # type: ignore[assignment]
    return out


# ── LLM call ───────────────────────────────────────────────────────────


async def _call_classifier_llm(
    *,
    user_id: str,
    config: EntityRecoveryConfig,
    llm_client: LLMClientProtocol,
    system: str,
    user: str,
    n_items: int,
) -> str:
    """One classifier chat call. Returns content string; raises ValueError
    on any non-usable outcome (mirrors pass2_filter._call_filter_llm)."""
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            transient_retry_budget=config.transient_retry_budget,
            **build_recovery_submit_kwargs(
                config=config, system=system, user=user, n_items=n_items,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"recovery LLM call failed: {exc}") from exc
    return parse_recovery_job(job)


# ── Decouple seams (LLM re-arch Phase 2b WX-T2b) — see extractors/entity.py ──


def build_recovery_submit_kwargs(
    *, config: "EntityRecoveryConfig", system: str, user: str, n_items: int,
) -> dict:
    """Pure: submit_and_wait / submit_job kwargs for the recovery classifier chat
    (user_id + transient_retry_budget stay per-call)."""
    max_tokens = 1024 + 200 * max(1, n_items)
    return dict(
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
            "chat_template_kwargs": {
                "thinking": False,
                "enable_thinking": False,
            },
        },
        chunking=None,
        job_meta={"extractor": "entity_recovery"},
    )


def parse_recovery_job(job) -> str:
    """Pure: validate the terminal Job + extract the classifier content. Raises
    ValueError on any non-usable outcome (so the per-batch caller marks the batch
    unjudged instead of aborting the recovery pass)."""
    if getattr(job, "status", None) != "completed":
        raise ValueError(
            f"recovery job ended status={getattr(job, 'status', '?')}"
        )
    result = getattr(job, "result", None) or {}
    # Mirror llm_judge.py:441 + pass2_filter._call_filter_llm:
    # gateway returns messages[0].content per
    # feedback_gateway_response_messages_array_not_content_string
    content = ""
    if isinstance(result, dict):
        messages = result.get("messages") or []
        if messages and isinstance(messages[0], dict):
            content = messages[0].get("content", "") or ""
        if not content:
            content = result.get("content", "") or ""
    if not content:
        raise ValueError("recovery job returned empty content")
    return content


# ── Public entry point ─────────────────────────────────────────────────


def _build_entity(
    name: str, kind: str, idx: int,
    *,
    user_id: str,
    project_id: str | None,
) -> LLMEntityCandidate:
    """Construct a minimal recovered entity. Uses canonical helpers so
    downstream writer ID-matching works the same as primary extraction."""
    canonical = name.lower()
    return LLMEntityCandidate.model_construct(
        name=name,
        kind=kind,
        aliases=[],
        confidence=0.7,  # marker: recovered, lower than primary extraction
        canonical_name=canonical,
        canonical_id=entity_canonical_id(user_id, project_id, canonical, kind),
    )


async def recover_missing_entities(
    candidates: Pass2Candidates,
    *,
    text: str,
    config: EntityRecoveryConfig,
    user_id: str,
    llm_client: LLMClientProtocol,
    project_id: str | None = None,
    on_decision: RecoveryDecisionHandler | None = None,
) -> Pass2Candidates:
    """3-tier entity recovery + abstract-relation cleanup.

    For each relation subject/object NOT in the candidate entity name
    set:
      Tier 1+2: lookup in config.known_entity_kinds (case-insensitive).
        If matched → promote as entity with the supplied kind.
      Tier 3: if not matched, ask LLM classifier "is this a proper
        entity?". If verdict=entity → promote; if verdict=abstract →
        drop all relations referencing this name; if unjudged → leave
        alone (writer will cascade-skip).

    Returns:
        New Pass2Candidates with:
          - entities: original + recovered
          - relations: original minus those referencing abstract names
          - events / facts / filter_status / filter_coverage: passed
            through unchanged
    """
    # MED-1: case-insensitive lookup map.
    known_lower = {k.lower(): v for k, v in config.known_entity_kinds.items()}

    entity_name_set = {e.name for e in candidates.entities}
    relations = candidates.relations

    # Collect unique unmatched names from relations.
    unmatched_names: list[str] = []
    seen: set[str] = set()
    for r in relations:
        for n in (r.subject, r.object):
            if n and n not in entity_name_set and n not in seen:
                unmatched_names.append(n)
                seen.add(n)

    # LOW-2: short-circuit if everything resolves.
    if not unmatched_names:
        return candidates

    promoted: list[LLMEntityCandidate] = []
    # MED-2: name→verdict so we apply consistently across all references.
    name_verdict: dict[str, VerdictLabel] = {}

    # Tier 1+2 — glossary/hints lookup.
    still_unmatched: list[str] = []
    for name in unmatched_names:
        kind = known_lower.get(name.lower())
        if kind:
            promoted.append(_build_entity(
                name, kind, len(promoted),
                user_id=user_id, project_id=project_id,
            ))
            name_verdict[name] = "entity"
            if on_decision is not None:
                try:
                    on_decision(RecoveryDecision(
                        name=name, verdict="entity",
                        source="glossary" if name.lower() in {k.lower() for k in config.known_entity_kinds} else "hints",
                        kind=kind,
                    ))
                except Exception:  # noqa: BLE001
                    logger.exception("on_decision callback raised")
        else:
            still_unmatched.append(name)

    # Tier 3 — LLM classifier for the rest.
    if still_unmatched:
        try:
            await _classify_remaining(
                still_unmatched,
                text=text, config=config, user_id=user_id,
                project_id=project_id,
                llm_client=llm_client,
                promoted_out=promoted,
                name_verdict_out=name_verdict,
                on_decision=on_decision,
            )
        except Exception as exc:  # noqa: BLE001
            # Best-effort: degrade to unjudged for the rest.
            logger.warning(
                "entity recovery LLM classifier failed: %s; "
                "%d names left as unmatched", exc, len(still_unmatched),
            )
            for name in still_unmatched:
                name_verdict[name] = "unjudged"
                if on_decision is not None:
                    try:
                        on_decision(RecoveryDecision(
                            name=name, verdict="unjudged", source="unmatched",
                        ))
                    except Exception:  # noqa: BLE001
                        logger.exception("on_decision callback raised")

    # Apply MED-2: drop relations referencing abstract names.
    abstract_names = {n for n, v in name_verdict.items() if v == "abstract"}
    if abstract_names:
        kept_relations = [
            r for r in relations
            if r.subject not in abstract_names
            and r.object not in abstract_names
        ]
    else:
        kept_relations = list(relations)

    return replace(
        candidates,
        entities=list(candidates.entities) + promoted,
        relations=kept_relations,
    )


async def _classify_remaining(
    names: list[str],
    *,
    text: str,
    config: EntityRecoveryConfig,
    user_id: str,
    project_id: str | None,
    llm_client: LLMClientProtocol,
    promoted_out: list[LLMEntityCandidate],
    name_verdict_out: dict[str, VerdictLabel],
    on_decision: RecoveryDecisionHandler | None,
) -> None:
    """Batch-call the LLM classifier on remaining unmatched names.

    Mutates `promoted_out` (adds new entities) and `name_verdict_out`
    (records verdict per name).
    """
    batch_size = config.max_items_per_batch
    for batch_start in range(0, len(names), batch_size):
        batch = names[batch_start : batch_start + batch_size]
        numbered = "\n".join(f"[{i}] {n}" for i, n in enumerate(batch))
        user_msg = (
            f"SOURCE TEXT:\n{text}\n\n"
            f"NAMES (classify each):\n{numbered}\n"
        )
        try:
            content = await _call_classifier_llm(
                user_id=user_id, config=config, llm_client=llm_client,
                system=_CLASSIFIER_SYSTEM, user=user_msg, n_items=len(batch),
            )
            decisions = _parse_decisions(content)
        except ValueError as exc:
            logger.warning(
                "recovery batch failed batch=[%d,%d): %s",
                batch_start, batch_start + len(batch), exc,
            )
            decisions = {}

        for local_idx, name in enumerate(batch):
            decision = decisions.get(local_idx)
            if decision is None:
                name_verdict_out[name] = "unjudged"
                if on_decision is not None:
                    try:
                        on_decision(RecoveryDecision(
                            name=name, verdict="unjudged", source="llm",
                        ))
                    except Exception:  # noqa: BLE001
                        logger.exception("on_decision callback raised")
                continue
            verdict, kind = decision
            name_verdict_out[name] = verdict
            if verdict == "entity":
                promoted_out.append(_build_entity(
                    name, kind, len(promoted_out),
                    user_id=user_id, project_id=project_id,
                ))
            if on_decision is not None:
                try:
                    on_decision(RecoveryDecision(
                        name=name, verdict=verdict,
                        source="llm", kind=kind if verdict == "entity" else None,
                    ))
                except Exception:  # noqa: BLE001
                    logger.exception("on_decision callback raised")
