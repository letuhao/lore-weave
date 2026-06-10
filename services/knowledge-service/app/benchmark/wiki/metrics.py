"""wiki-llm M8 — thin advisory quality metrics for AI-generated wiki articles.

Pure functions over the data the glossary API already exposes (M7b-1):
``generation_status`` on the list + ``generation_provenance`` + ``body_json`` on
the detail. No I/O — the runner does the fetching and feeds these.

Two metrics (MVP, deterministic → advisory band; LLM-judge groundedness is a
follow-up):

* **verify-flag-rate** — of the AI-generated articles, what share the
  CanonVerifier flagged (``needs_review``/``blocked``). A rising rate = the model
  + prompt are drifting off-canon.
* **citation-resolvability** — of the distinct citations actually rendered in an
  article's body, what share carry their *evidence* (a snippet) and an *anchor*
  (a chapter for a passage cite). An unresolvable citation is one the reader
  cannot verify — the anti-hallucination promise of the citation chip broken.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "verify_flag_rate",
    "collect_citation_marks",
    "citation_resolvability",
    "aggregate_resolvability",
]

# generation_status values written by M5 (NULL = human-authored, excluded).
_AI_STATUSES = ("generated", "needs_review", "blocked")
_FLAGGED = ("needs_review", "blocked")


def verify_flag_rate(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Over wiki-list items, count AI articles by ``generation_status`` and the
    flagged share. Human-authored articles (status None) are excluded from the
    denominator. ``flagged_rate`` is 0.0 when there are no AI articles."""
    by_status = {s: 0 for s in _AI_STATUSES}
    for a in articles:
        st = a.get("generation_status")
        if st in by_status:
            by_status[st] += 1
    total_ai = sum(by_status.values())
    flagged = sum(by_status[s] for s in _FLAGGED)
    return {
        "total_ai": total_ai,
        **by_status,
        "flagged": flagged,
        "flagged_rate": (flagged / total_ai) if total_ai else 0.0,
        "clean_rate": (by_status["generated"] / total_ai) if total_ai else 0.0,
    }


def collect_citation_marks(body_json: Any) -> dict[str, dict[str, Any]]:
    """Walk a TipTap doc and collect the DISTINCT citation marks by ``cite_id``
    (the body prose and the References list repeat the same cite_id — we want one
    entry per citation, with its attrs). Returns ``{cite_id: attrs}``."""
    out: dict[str, dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
            return
        if not isinstance(node, dict):
            return
        for mark in node.get("marks") or []:
            if isinstance(mark, dict) and mark.get("type") == "citation":
                attrs = mark.get("attrs") or {}
                cid = attrs.get("cite_id")
                if cid and cid not in out:
                    out[cid] = attrs
        walk(node.get("content"))

    walk(body_json)
    return out


def _is_resolvable(attrs: dict[str, Any]) -> bool:
    """A citation resolves when the reader can verify it: it carries a non-empty
    snippet (shown in the popover) AND, for a passage/chapter source, an anchor to
    jump to (``chapter_id``). Glossary/KG sources resolve on the snippet alone
    (there is no chapter to jump to)."""
    snippet = (attrs.get("snippet") or "").strip()
    if not snippet:
        return False
    source_type = attrs.get("source_type") or "passage"
    if source_type in ("passage", "chapter"):
        return bool(attrs.get("chapter_id"))
    return True


def citation_resolvability(detail: dict[str, Any]) -> dict[str, Any]:
    """For ONE article detail: of its distinct rendered citations, how many are
    resolvable. ``ratio`` is 1.0 for an article with no citations (vacuously fine
    — a stub with no claims to cite). ``declared`` is the provenance citation count
    for context (a large gap vs ``total`` hints the body dropped cites)."""
    marks = collect_citation_marks(detail.get("body_json"))
    total = len(marks)
    resolvable = sum(1 for a in marks.values() if _is_resolvable(a))
    provenance = detail.get("generation_provenance") or {}
    declared = len(provenance.get("citations") or [])
    return {
        "total": total,
        "resolvable": resolvable,
        "ratio": (resolvable / total) if total else 1.0,
        "declared": declared,
    }


def aggregate_resolvability(per_article: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-article resolvability into a corpus number: the micro-average
    (sum resolvable / sum total) so articles with more citations weigh more, plus
    the count of articles with any unresolvable citation."""
    sum_total = sum(r["total"] for r in per_article)
    sum_resolvable = sum(r["resolvable"] for r in per_article)
    with_unresolvable = sum(1 for r in per_article if r["resolvable"] < r["total"])
    return {
        "articles": len(per_article),
        "citations": sum_total,
        "resolvable": sum_resolvable,
        "ratio": (sum_resolvable / sum_total) if sum_total else 1.0,
        "articles_with_unresolvable": with_unresolvable,
    }
