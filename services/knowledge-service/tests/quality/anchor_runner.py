"""Anchor benchmark runners for the eval framework overhaul cycle (2026-05-27).

Provides two anchor-point measurements against published-baseline datasets, so
our narrative-fiction extraction quality has an external truth signal beyond
custom 10-chapter fixtures + LLM-judge.

- `run_conll2003_anchor` — token-level NER F1 against CoNLL-2003 test split
  (English news domain, strict span match). RoBERTa-large baseline ≈ 92.4 F1.
- `run_docred_anchor` — unlabeled relation-triple F1 against DocRED validation
  split (English Wikipedia, 96 relation types, but we score UNLABELED-F1 — triple
  existence ignoring our 28→96 predicate mapping per spec Q3).

Per spec D2 + HIGH-1 (sanity-floor fix): each runner emits `passes_sanity_floor`
based on (F1 ≥ 0.10 AND N_extracted ≥ 0.1 × N_gold per-sample average). The
sanity floor is a hard gate against extractor-regressed-to-empty (wasserstein-
style), NOT a quality gate. Actual F1 numbers are informational anchors.

Data sources (verified loadable as of cycle date):
- CoNLL-2003: `tner/conll2003` test split (3453 examples; legacy `conll2003`
  builder script removed from HF Hub)
- DocRED: `thunlp/docred` validation split (998 examples; requires
  `trust_remote_code=True`)

The runners are independent of our extractor module — they take a callable
`extractor_fn(text: str) -> ExtractorOutput` so any extractor (current loreweave
gateway pipeline, future direct-stream variant, or even a mock for unit tests)
can be anchored.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)


# ── Canonical CoNLL-2003 label scheme (tner/conll2003 ID → tag string) ────────
# Per the standard CoNLL-2003 9-class BIO scheme. Verified by inspection of
# tner/conll2003 test split: e.g., "JAPAN" tagged 5 = B-LOC fits.
_CONLL2003_ID_TO_TAG: dict[int, str] = {
    0: "O",
    1: "B-PER",
    2: "I-PER",
    3: "B-ORG",
    4: "I-ORG",
    5: "B-LOC",
    6: "I-LOC",
    7: "B-MISC",
    8: "I-MISC",
}


# Our extractor's kind enum → CoNLL kind mapping (4 CoNLL classes).
# `concept` + `other` → MISC (catch-all). `artifact` → MISC (not a strict CoNLL class).
_KIND_TO_CONLL_KIND: dict[str, str] = {
    "person": "PER",
    "organization": "ORG",
    "place": "LOC",
    "artifact": "MISC",
    "concept": "MISC",
    "other": "MISC",
}


@dataclass
class ExtractedEntity:
    """Minimal entity shape for anchor scoring (decoupled from
    `LLMEntityCandidate` to avoid SDK coupling). `name` is the surface form
    as extracted; `kind` is in our 6-class enum."""

    name: str
    kind: str


@dataclass
class CoNLLAnchorReport:
    """Result of one CoNLL-2003 anchor run."""

    dataset: str
    split: str
    n_samples: int
    avg_n_extracted: float
    avg_n_gold: float
    precision: float
    recall: float
    f1: float
    per_class_f1: dict[str, float] = field(default_factory=dict)
    passes_sanity_floor: bool = False
    sanity_floor_reason: str = ""


@dataclass
class DocREDAnchorReport:
    """Result of one DocRED unlabeled-triple anchor run."""

    dataset: str
    split: str
    n_samples: int
    avg_n_extracted: float
    avg_n_gold: float
    precision: float
    recall: float
    f1: float
    passes_sanity_floor: bool = False
    sanity_floor_reason: str = ""


# Sanity-floor parameters per spec D2 HIGH-1 fix.
_SANITY_FLOOR_F1 = 0.10
_SANITY_FLOOR_EXTRACTED_RATIO = 0.10  # N_extracted ≥ 0.1 × N_gold


def _check_sanity_floor(
    *,
    f1: float,
    avg_n_extracted: float,
    avg_n_gold: float,
) -> tuple[bool, str]:
    """Sanity floor: catch extractor-regressed-to-empty (HIGH-1 trap).

    Returns (passes, reason_if_failed).
    """
    if f1 < _SANITY_FLOOR_F1:
        return False, f"F1={f1:.3f} < floor {_SANITY_FLOOR_F1}"
    if avg_n_gold > 0 and avg_n_extracted < _SANITY_FLOOR_EXTRACTED_RATIO * avg_n_gold:
        return False, (
            f"avg_n_extracted={avg_n_extracted:.1f} < "
            f"{_SANITY_FLOOR_EXTRACTED_RATIO} × avg_n_gold={avg_n_gold:.1f}"
        )
    return True, ""


# ── CoNLL-2003 anchor ─────────────────────────────────────────────────────────


def _build_token_text_and_span_map(tokens: Sequence[str]) -> tuple[str, list[tuple[int, int]]]:
    """Join tokens by single space; return joined text + (start, end) char
    offsets per token. Spans are half-open `[start, end)` for str slicing."""

    text_parts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    for i, tok in enumerate(tokens):
        if i > 0:
            text_parts.append(" ")
            cursor += 1
        text_parts.append(tok)
        spans.append((cursor, cursor + len(tok)))
        cursor += len(tok)
    return "".join(text_parts), spans


def _align_entities_to_bio(
    tokens: Sequence[str],
    entities: Sequence[ExtractedEntity],
) -> list[str]:
    """Convert extracted (name, kind) entities to BIO/IOB token-tag sequence.

    Algorithm (case-sensitive whole-word per spec D2 Risk 4 mitigation):
      1. Build joined text from tokens with char-offset spans.
      2. For each extracted entity, find the FIRST case-sensitive occurrence
         of `name` as a contiguous span in the joined text whose start aligns
         with a token boundary AND whose end aligns with a token boundary.
      3. Mark the matching tokens with B-{kind}/I-{kind}; unclaimed tokens stay O.
      4. Conflicts: first-write-wins (already-tagged tokens skipped).

    Imperfect by design (per spec Risk 4 — we lose precision because our
    extractor doesn't return char spans). Documented as lower-bound F1.
    """

    joined, spans = _build_token_text_and_span_map(tokens)
    # span_starts[char_offset] = token_index where a token starts; else -1
    span_starts: dict[int, int] = {start: i for i, (start, _end) in enumerate(spans)}
    span_ends: dict[int, int] = {end: i for i, (_start, end) in enumerate(spans)}
    tags = ["O"] * len(tokens)

    for ent in entities:
        if not ent.name:
            continue
        conll_kind = _KIND_TO_CONLL_KIND.get(ent.kind, "MISC")
        # Find first case-sensitive occurrence aligning with token boundaries.
        search_from = 0
        while True:
            idx = joined.find(ent.name, search_from)
            if idx == -1:
                break
            start_tok = span_starts.get(idx)
            end_tok = span_ends.get(idx + len(ent.name))
            if start_tok is not None and end_tok is not None and end_tok >= start_tok:
                # Token range is [start_tok, end_tok] inclusive.
                if all(tags[t] == "O" for t in range(start_tok, end_tok + 1)):
                    tags[start_tok] = f"B-{conll_kind}"
                    for t in range(start_tok + 1, end_tok + 1):
                        tags[t] = f"I-{conll_kind}"
                    break
            search_from = idx + 1
    return tags


async def run_conll2003_anchor(
    extractor_fn: Callable[[str], Awaitable[Sequence[ExtractedEntity]]],
    *,
    n_samples: int = 100,
    split: str = "test",
    hf_cache_dir: str | None = None,
) -> CoNLLAnchorReport:
    """Run CoNLL-2003 entity anchor against an async extractor.

    Args:
        extractor_fn: async callable taking joined-text and returning a list
            of `ExtractedEntity`. Caller is responsible for wiring this to
            the production extractor with appropriate context_budget etc.
        n_samples: how many test examples to evaluate (default 100; spec Q1).
        split: HF split string; default "test" for canonical CoNLL-2003.
        hf_cache_dir: optional override for HF_DATASETS_CACHE env var.

    Returns:
        `CoNLLAnchorReport` with F1, per-class F1, sanity-floor result.
    """

    if hf_cache_dir:
        os.environ["HF_DATASETS_CACHE"] = hf_cache_dir

    # Defer import so the module imports even when datasets isn't installed
    # (e.g., on a host pytest collection that doesn't need anchors).
    from datasets import load_dataset
    from seqeval.metrics import classification_report, f1_score, precision_score, recall_score

    logger.info("Loading tner/conll2003 split=%s[:%d]", split, n_samples)
    ds = load_dataset("tner/conll2003", split=f"{split}[:{n_samples}]")
    logger.info("Loaded %d CoNLL examples", len(ds))

    gold_tag_seqs: list[list[str]] = []
    pred_tag_seqs: list[list[str]] = []
    n_extracted_total = 0
    n_gold_total = 0

    for ex in ds:
        tokens = ex["tokens"]
        gold_tag_ids = ex["tags"]
        gold_tags = [_CONLL2003_ID_TO_TAG.get(tid, "O") for tid in gold_tag_ids]

        joined_text, _spans = _build_token_text_and_span_map(tokens)
        extracted = list(await extractor_fn(joined_text))
        pred_tags = _align_entities_to_bio(tokens, extracted)

        gold_tag_seqs.append(gold_tags)
        pred_tag_seqs.append(pred_tags)

        n_extracted_total += len(extracted)
        # Count gold entities = number of B- tags in gold (each B starts one entity)
        n_gold_total += sum(1 for t in gold_tags if t.startswith("B-"))

    p = float(precision_score(gold_tag_seqs, pred_tag_seqs, mode="strict"))
    r = float(recall_score(gold_tag_seqs, pred_tag_seqs, mode="strict"))
    f1 = float(f1_score(gold_tag_seqs, pred_tag_seqs, mode="strict"))

    # Per-class F1 via classification_report. Returns dict when output_dict=True.
    cls_report = classification_report(
        gold_tag_seqs, pred_tag_seqs, mode="strict", output_dict=True, zero_division=0
    )
    per_class_f1 = {
        kind: float(stats["f1-score"])
        for kind, stats in cls_report.items()
        if isinstance(stats, dict) and kind not in {"micro avg", "macro avg", "weighted avg"}
    }

    n_samples_actual = len(ds)
    avg_n_extracted = n_extracted_total / n_samples_actual if n_samples_actual else 0.0
    avg_n_gold = n_gold_total / n_samples_actual if n_samples_actual else 0.0
    passes, reason = _check_sanity_floor(
        f1=f1, avg_n_extracted=avg_n_extracted, avg_n_gold=avg_n_gold
    )

    return CoNLLAnchorReport(
        dataset="tner/conll2003",
        split=split,
        n_samples=n_samples_actual,
        avg_n_extracted=avg_n_extracted,
        avg_n_gold=avg_n_gold,
        precision=p,
        recall=r,
        f1=f1,
        per_class_f1=per_class_f1,
        passes_sanity_floor=passes,
        sanity_floor_reason=reason,
    )


# ── DocRED unlabeled-triple anchor ────────────────────────────────────────────


@dataclass
class ExtractedTriple:
    """Minimal triple shape: (subject_name, object_name). UNLABELED — predicate
    is ignored for the F1 computation (spec Q3 — typed-mapping deferred)."""

    subject: str
    object_: str


def _docred_gold_triples(example: dict[str, Any]) -> set[frozenset[str]]:
    """Extract gold (subject_name, object_name) pairs from a DocRED example.

    DocRED stores:
      - sents: list[list[str]] tokenized sentences
      - vertexSet: list[list[dict]] entities. Each entity = list of mentions;
        each mention = {sent_id, pos: [start, end], name, type}.
      - labels: list[dict] with h (head vertex index), t (tail), r (relation).

    For each label entry, take the FIRST mention name of the head + tail
    vertices as the canonical surface form. Return a set of unordered pairs
    (frozenset of 2 strings) — direction-agnostic for unlabeled scoring per
    spec Q3.
    """

    vertices: list[list[dict[str, Any]]] = example.get("vertexSet", [])
    labels = example.get("labels", {})
    # Normalize labels — DocRED can have labels as dict-of-lists OR list-of-dicts.
    if isinstance(labels, dict):
        head_list = labels.get("head", [])
        tail_list = labels.get("tail", [])
        label_pairs = list(zip(head_list, tail_list))
    else:
        label_pairs = [(item.get("h"), item.get("t")) for item in labels]

    triples: set[frozenset[str]] = set()
    for h, t in label_pairs:
        if h is None or t is None:
            continue
        if h < 0 or h >= len(vertices) or t < 0 or t >= len(vertices):
            continue
        if not vertices[h] or not vertices[t]:
            continue
        head_name = vertices[h][0].get("name", "")
        tail_name = vertices[t][0].get("name", "")
        if head_name and tail_name and head_name != tail_name:
            triples.add(frozenset((head_name, tail_name)))
    return triples


def _docred_text(example: dict[str, Any]) -> str:
    """Reassemble the article text from DocRED's tokenized sentences."""

    sents: list[list[str]] = example.get("sents", [])
    return " ".join(" ".join(tokens) for tokens in sents)


async def run_docred_anchor(
    extractor_fn: Callable[[str], Awaitable[Sequence[ExtractedTriple]]],
    *,
    n_samples: int = 100,
    split: str = "validation",
    hf_cache_dir: str | None = None,
) -> DocREDAnchorReport:
    """Run DocRED unlabeled-triple anchor against an async extractor.

    Spec Q3: UNLABELED-F1 only (triple existence as unordered pair, ignoring
    our predicate vocabulary's mismatch with DocRED's 96 typed relations).
    """

    if hf_cache_dir:
        os.environ["HF_DATASETS_CACHE"] = hf_cache_dir

    from datasets import load_dataset

    logger.info("Loading thunlp/docred split=%s[:%d]", split, n_samples)
    ds = load_dataset(
        "thunlp/docred", split=f"{split}[:{n_samples}]", trust_remote_code=True
    )
    logger.info("Loaded %d DocRED examples", len(ds))

    tp = fp = fn = 0
    n_extracted_total = 0
    n_gold_total = 0

    for ex in ds:
        text = _docred_text(ex)
        gold_pairs = _docred_gold_triples(ex)
        n_gold_total += len(gold_pairs)

        extracted = list(await extractor_fn(text))
        n_extracted_total += len(extracted)

        pred_pairs: set[frozenset[str]] = set()
        for tr in extracted:
            if tr.subject and tr.object_ and tr.subject != tr.object_:
                pred_pairs.add(frozenset((tr.subject, tr.object_)))

        tp += len(pred_pairs & gold_pairs)
        fp += len(pred_pairs - gold_pairs)
        fn += len(gold_pairs - pred_pairs)

    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * p * r) / (p + r) if (p + r) else 0.0

    n_samples_actual = len(ds)
    avg_n_extracted = n_extracted_total / n_samples_actual if n_samples_actual else 0.0
    avg_n_gold = n_gold_total / n_samples_actual if n_samples_actual else 0.0
    passes, reason = _check_sanity_floor(
        f1=f1, avg_n_extracted=avg_n_extracted, avg_n_gold=avg_n_gold
    )

    return DocREDAnchorReport(
        dataset="thunlp/docred",
        split=split,
        n_samples=n_samples_actual,
        avg_n_extracted=avg_n_extracted,
        avg_n_gold=avg_n_gold,
        precision=p,
        recall=r,
        f1=f1,
        passes_sanity_floor=passes,
        sanity_floor_reason=reason,
    )


# ── Report persistence ───────────────────────────────────────────────────────


def write_anchor_report(
    report: CoNLLAnchorReport | DocREDAnchorReport,
    out_dir: Path,
) -> Path:
    """Persist an anchor report as JSON for downstream comparison."""

    import json

    out_dir.mkdir(parents=True, exist_ok=True)
    name = "conll2003_anchor.json" if isinstance(report, CoNLLAnchorReport) else "docred_anchor.json"
    out_path = out_dir / name
    out_path.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path
